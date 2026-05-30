# 前端代码质量工具链

> 建立日期: 2026-05-30
> 关联: eslint.config.js, .prettierrc, .husky/pre-commit, scripts/check-ts-syntax.cjs

## 问题

AI 写前端代码（`.tsx`/`.ts`）时，漏括号、漏闭合标签导致 JS 运行时错误，页面白屏或崩溃。`write_file` 工具对 `.py/.json/.yaml` 做自动语法校验，但对前端文件不做。

## 解决方案：三层防御链

```
Layer 1 ── 语法校验（写完立即跑）   → check-ts-syntax.cjs
Layer 2 ── 批量检查（改完一批跑）   → pnpm lint:fix (ESLint + Prettier)
Layer 3 ── git 拦截（提交时自动跑） → Husky → lint-staged → prettier + eslint --fix
```

### Layer 1: 语法校验脚本

`frontend/scripts/check-ts-syntax.cjs`

用项目自带的 TypeScript parser 做纯语法检查，0.1s 完成，不依赖额外包。检查项：
- 缺括号: `useState(0` → `',' expected`
- 缺闭合标签: `<span>...</div>` → `JSX element has no corresponding closing tag`

```bash
node scripts/check-ts-syntax.cjs src/components/Xxx.tsx
```

**注意**：项目 `package.json` 有 `"type": "module"`，`.js` 文件自动视为 ES module。必须用 `.cjs` 扩展名才能使用 `require()`。

### Layer 2: ESLint + Prettier

#### 安装的包

| 包 | 版本 | 作用 |
|----------------|:------:|------|
| `eslint` | 10.4.0 | 核心 |
| `@eslint/js` | 10.0.1 | 推荐规则集 |
| `typescript-eslint` | 8.60.0 | TypeScript 类型感知规则 |
| `eslint-plugin-react-hooks` | 7.1.1 | React Hooks 规则 |
| `eslint-plugin-react-refresh` | 0.5.2 | Vite HMR 规则 |
| `globals` | 17.6.0 | 浏览器环境全局变量 |
| `eslint-config-prettier` | 10.1.8 | 关掉 ESLint 中与 Prettier 冲突的规则 |
| `prettier` | 3.8.3 | 代码格式化 |
| `husky` | 9.1.7 | git hooks 管理 |
| `lint-staged` | 17.0.5 | 只对 staged 文件跑 lint |

#### ESLint 配置

`eslint.config.js`（flat config 格式）：

```js
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import prettier from 'eslint-config-prettier'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: { ecmaVersion: 2020, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
  prettier,  // 最后加载，覆盖冲突规则
)
```

#### Prettier 配置

`.prettierrc`：

```json
{
  "semi": true,
  "singleQuote": true,
  "trailingComma": "es5",
  "tabWidth": 2,
  "printWidth": 100,
  "jsxSingleQuote": false,
  "bracketSpacing": true,
  "arrowParens": "always",
  "endOfLine": "lf"
}
```

#### npm scripts

```json
"scripts": {
  "lint": "eslint .",
  "lint:fix": "eslint . --fix",
  "format": "prettier --write \"src/**/*.{ts,tsx,json,css,md}\""
}
```

### Layer 3: Husky + lint-staged

#### 配

由于项目 git 根目录是 `~/zuoshanke/` 但 `package.json` 在 `frontend/` 下，Husky 无法直接 `init`：

```bash
mkdir -p frontend/.husky
cat > frontend/.husky/pre-commit << 'HOOK'
#!/usr/bin/env sh
cd frontend && pnpm lint-staged
HOOK
chmod +x frontend/.husky/pre-commit
cd ~/zuoshanke && git config core.hooksPath frontend/.husky
```

#### Hook 内容

```bash
#!/usr/bin/env sh
cd frontend && pnpm lint-staged
```

**关键**：必须 `cd frontend`，因为 lint-staged 需要在有 `package.json` 的目录运行。

#### lint-staged 配置（package.json 中）

```json
"lint-staged": {
  "*.{ts,tsx}": ["prettier --write", "eslint --fix"],
  "*.{json,md,css}": ["prettier --write"]
}
```

## 验证

```bash
# 语法校验
node scripts/check-ts-syntax.cjs src/App.tsx
# → ✅ src/App.tsx — 语法正确

# ESLint
pnpm lint
# → 无 error / 有 warning（no-explicit-any 等）

# Husky 拦截测试
echo 'const Bad = () => { return <div><span>broken</div> };' > src/__test-bad.tsx
git add src/__test-bad.tsx && git commit -m "should fail"
# → ✖ prettier --write: SyntaxError
# → 提交被退回
```

## 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| ESLint 版本 | v10 flat config | Vite 官方推荐，免 .eslintrc 兼容层 |
| 校验顺序 | check-ts-syntax → ESLint → Husky | 快→慢，写完立刻反馈 vs 提交时兜底 |
| husky hook 路径 | `frontend/.husky/` | 项目根无 package.json，只能设在子目录 |
| 不装 prettier-plugin-tailwindcss | 未用 Tailwind | 项目用纯 CSS，不需要 |
| 不装 eslint-plugin-import | 已有 TypeScript 的类型检查 | 避免规则冗余 |
