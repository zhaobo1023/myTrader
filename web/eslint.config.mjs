import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    rules: {
      // useEffect 中 setState 在 Next.js 16 + React 19 中是常见模式
      "react-hooks/set-state-in-effect": "off",
      // 渐进式类型收紧，暂不强制禁止 any
      "@typescript-eslint/no-explicit-any": "warn",
      // JSX 中引号转义过于严格
      "react/no-unescaped-entities": "off",
    },
  },
]);

export default eslintConfig;
