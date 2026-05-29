#!/usr/bin/env node
const ts = require('typescript');
const fs = require('fs');

const filePath = process.argv[2];
if (!filePath) {
  console.error('用法: node check-ts-syntax.js <文件路径>');
  process.exit(1);
}

const code = fs.readFileSync(filePath, 'utf8');
const sourceFile = ts.createSourceFile(filePath, code, ts.ScriptTarget.Latest, true);
const diag = sourceFile.parseDiagnostics || [];

if (diag.length > 0) {
  let hasError = false;
  diag.forEach(d => {
    if (d.category === ts.DiagnosticCategory.Error) {
      const pos = sourceFile.getLineAndCharacterOfPosition(d.start);
      console.error(`❌ ${filePath}:${pos.line + 1}:${pos.character + 1} — ${ts.flattenDiagnosticMessageText(d.messageText)}`);
      hasError = true;
    }
  });
  process.exit(hasError ? 1 : 0);
} else {
  console.log(`✅ ${filePath} — 语法正确`);
  process.exit(0);
}
