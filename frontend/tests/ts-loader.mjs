/**
 * Tiny, dependency-neutral ESM TypeScript test loader.
 * Uses the already pinned TypeScript devDependency. Compatible with Node 18+.
 * This loader is only used by the offline unit-test command.
 */
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const TYPESCRIPT_MODULE = /\.(?:ts|mts|cts|tsx)$/i;

export async function load(url, context, nextLoad) {
  if (!url.startsWith('file:') || !TYPESCRIPT_MODULE.test(new URL(url).pathname)) {
    return nextLoad(url, context);
  }
  const filename = fileURLToPath(url);
  const source = await readFile(filename, 'utf8');
  const result = ts.transpileModule(source, {
    fileName: filename,
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
      jsx: ts.JsxEmit.ReactJSX,
    },
    reportDiagnostics: true,
  });
  const errors = (result.diagnostics ?? []).filter((d) => d.category === ts.DiagnosticCategory.Error);
  if (errors.length) {
    throw new Error(ts.formatDiagnosticsWithColorAndContext(errors, {
      getCanonicalFileName: (file) => file,
      getCurrentDirectory: () => process.cwd(),
      getNewLine: () => '\n',
    }));
  }
  return { format: 'module', shortCircuit: true, source: result.outputText };
}
