// CC Switch's request/extractor convention in a capability-free QuickJS VM.
// Neither Node, filesystem, network, nor host objects are exposed to the script.
import { getQuickJS } from 'quickjs-emscripten';
let input = '';
for await (const chunk of process.stdin) {
  input += chunk;
  if (input.length > 3_000_000) process.exit(2);
}
const payload = JSON.parse(input);
const quickjs = await getQuickJS();
const runtime = quickjs.newRuntime();
runtime.setMemoryLimit(16 * 1024 * 1024);
runtime.setMaxStackSize(256 * 1024);
const deadline = Date.now() + 500;
runtime.setInterruptHandler(() => Date.now() > deadline);
const vm = runtime.newContext();
try {
  const code = String(payload.code).trim().replace(/;\s*$/, '');
  const expression = payload.stage === 'request'
    ? `JSON.stringify((${code}).request)`
    : `JSON.stringify((${code}).extractor(${JSON.stringify(payload.response)}))`;
  const result = vm.evalCode(expression);
  if (result.error) {
    result.error.dispose();
    process.stdout.write(JSON.stringify({error: '脚本执行失败或超过资源限制'}));
  } else {
    const raw = vm.getString(result.value);
    result.value.dispose();
    if (!raw || raw.length > 1_000_000) throw new Error('Invalid result');
    process.stdout.write(JSON.stringify({result: JSON.parse(raw)}));
  }
} catch {
  process.stdout.write(JSON.stringify({error: '脚本未返回可用的 JSON'}));
} finally {
  vm.dispose();
  runtime.dispose();
}
