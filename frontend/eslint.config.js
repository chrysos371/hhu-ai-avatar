import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import globals from 'globals';
export default tseslint.config({ignores:['dist','node_modules','playwright-report','test-results']},js.configs.recommended,...tseslint.configs.recommended,{files:['**/*.{ts,tsx}'],languageOptions:{globals:{...globals.browser,...globals.node,...globals.vitest}},rules:{'@typescript-eslint/no-explicit-any':'off'}});
