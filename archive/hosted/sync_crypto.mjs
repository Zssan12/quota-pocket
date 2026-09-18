import nacl from './vendor/nacl-fast.cjs';
import {randomBytes} from 'node:crypto';
let input='';
for await(const chunk of process.stdin){input+=chunk;if(input.length>500000)process.exit(2);}
try{
 const {key,room,seq,snapshot}=JSON.parse(input);
 const secret=Buffer.from(key,'base64');if(secret.length!==32||!/^\w{32}$/.test(room)||!Number.isSafeInteger(seq)||seq<1)throw Error();
 const payload=Buffer.from(JSON.stringify({v:1,room,seq,publishedAt:Date.now(),snapshot}));
 if(payload.length>380000)throw Error();
 const nonce=randomBytes(24),cipher=nacl.secretbox(payload,nonce,secret);
 process.stdout.write(JSON.stringify({v:1,room,seq,nonce:nonce.toString('base64'),ciphertext:Buffer.from(cipher).toString('base64')}));
}catch{process.stderr.write('Snapshot encryption failed.');process.exit(2);}
