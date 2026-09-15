//! Opt-in, local-only export of values already received by UsageCache.
//! No HTTP, credentials, polling, or changes to the upstream refresh schedule.
use std::collections::BTreeMap;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use crate::provider::UsageResult;
use crate::services::subscription::SubscriptionQuota;

type Key = (String, String, String);

pub(super) struct PocketExport {
    path: Option<PathBuf>,
    entries: Mutex<BTreeMap<Key, Value>>,
}

fn seconds() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs()
}

fn text(value: &str) -> String {
    value.chars().take(80).collect()
}

impl Default for PocketExport {
    fn default() -> Self {
        // The parent must already exist. Export never changes application config.
        let path = std::env::var_os("CC_SWITCH_QUOTA_EXPORT")
            .map(PathBuf::from)
            .filter(|p| p.is_absolute() && p.file_name().is_some());
        let exporter = Self { path, entries: Mutex::new(BTreeMap::new()) };
        // A new CC Switch process starts with an empty cache, not yesterday's file.
        exporter.clear();
        exporter
    }
}

fn script_value(app: &str, provider: &str, result: &UsageResult) -> Value {
    let data: Vec<Value> = result.data.iter().flatten().map(|entry| json!({
        "planName": entry.plan_name.as_deref().map(text),
        "remaining": entry.remaining,
        "unit": entry.unit.as_deref().map(text),
        "isValid": entry.is_valid,
    })).collect();
    json!({"kind": "script", "appType": app, "providerId": provider,
           "observedAt": seconds(), "success": result.success, "data": data})
}

fn subscription_value(kind: &str, app: &str, account: &str, quota: &SubscriptionQuota) -> Value {
    let tiers: Vec<Value> = quota.tiers.iter().map(|tier| json!({
        "name": text(&tier.name), "utilization": tier.utilization,
        "resetsAt": tier.resets_at.as_deref().map(text),
    })).collect();
    // queried_at is milliseconds in the pinned CC Switch revision.
    let observed = quota.queried_at.filter(|v| *v > 0)
        .map(|v| v as u64 / 1000).unwrap_or_else(seconds);
    json!({"kind": kind, "appType": app, "accountId": account,
           "observedAt": observed, "success": quota.success, "tiers": tiers})
}

impl PocketExport {
    fn publish(&self, entries: &BTreeMap<Key, Value>) -> std::io::Result<()> {
        let Some(path) = &self.path else { return Ok(()); };
        let parent = path.parent().ok_or(std::io::ErrorKind::InvalidInput)?;
        let values: Vec<&Value> = entries.values().collect();
        let packet = json!({"schemaVersion": 1, "source": "cc-switch-usage-cache",
                            "exportedAt": seconds(), "entries": values});
        let bytes = serde_json::to_vec(&packet)?;
        // Same-directory atomic replacement: readers see one complete generation.
        let mut file = tempfile::NamedTempFile::new_in(parent)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            file.as_file().set_permissions(std::fs::Permissions::from_mode(0o600))?;
        }
        file.write_all(&bytes)?;
        file.as_file().sync_all()?;
        file.persist(path).map_err(|error| error.error)?;
        Ok(())
    }

    fn change(&self, update: impl FnOnce(&mut BTreeMap<Key, Value>)) {
        if self.path.is_none() { return; }
        if let Ok(mut entries) = self.entries.lock() {
            update(&mut entries);
            if self.publish(&entries).is_err() {
                // Do not log the configured path, raw results, or credentials.
                log::warn!("Quota cache export failed; normal CC Switch queries are unaffected");
            }
        }
    }

    pub(super) fn script(&self, app: &str, provider: &str, result: &UsageResult) {
        if self.path.is_none() { return; }
        let key = ("script".into(), app.into(), provider.into());
        self.change(|entries| { entries.insert(key, script_value(app, provider, result)); });
    }

    pub(super) fn subscription(&self, kind: &str, app: &str, account: &str, quota: &SubscriptionQuota) {
        if self.path.is_none() { return; }
        let key = (kind.into(), app.into(), account.into());
        self.change(|entries| { entries.insert(key, subscription_value(kind, app, account, quota)); });
    }

    pub(super) fn invalidate(&self, kind: &str, app: &str, identity: &str) {
        let key = (kind.into(), app.into(), identity.into());
        self.change(|entries| { entries.remove(&key); });
    }

    pub(super) fn clear(&self) {
        self.change(|entries| entries.clear());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::provider::UsageData;
    use crate::services::subscription::{CredentialStatus, QuotaTier};

    #[test]
    fn script_projection_keeps_zero_but_omits_raw_errors_and_extra_fields() {
        let result = UsageResult { success: true, error: Some("SECRET".into()), data: Some(vec![UsageData {
            plan_name: Some("Plan".into()), extra: Some("SECRET".into()),
            is_valid: Some(true), invalid_message: Some("SECRET".into()),
            total: Some(999.0), used: Some(999.0), remaining: Some(0.0), unit: Some("USD".into()),
        }]) };
        let value = script_value("codex", "p", &result);
        assert_eq!(value["data"][0]["remaining"], 0.0);
        assert!(!value.to_string().contains("SECRET"));
        assert!(!value.to_string().contains("999"));
    }

    #[test]
    fn subscription_projection_preserves_source_time_and_omits_credentials() {
        let quota = SubscriptionQuota {
            tool: "claude".into(), credential_status: CredentialStatus::Valid,
            credential_message: Some("SECRET".into()), success: true, error: None,
            queried_at: Some(1_800_000_000_000), extra_usage: None,
            tiers: vec![QuotaTier { name: "five_hour".into(), utilization: 25.0,
                resets_at: None, used_value_usd: Some(999.0), max_value_usd: None }],
        };
        let value = subscription_value("subscription", "claude", "", &quota);
        assert_eq!(value["observedAt"], 1_800_000_000_u64);
        assert_eq!(value["tiers"][0]["utilization"], 25.0);
        assert!(!value.to_string().contains("SECRET"));
        assert!(!value.to_string().contains("999"));
    }
}
