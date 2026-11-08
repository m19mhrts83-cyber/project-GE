import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

/** lib/*.ts（import の無い純粋な部品）を読み込む */
export function loadLib(name) {
  const source = readFileSync(new URL(`../lib/${name}.ts`, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(code, {
    URLSearchParams,
    exports, Date, Math, RegExp, Array, Object, Number, String, Set, Map, JSON,
    crypto: globalThis.crypto, TextEncoder, btoa, Uint8Array,
  });
  return exports;
}
