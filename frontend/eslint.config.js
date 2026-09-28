import js from '@eslint/js';
import react from 'eslint-plugin-react';
import hooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

// §14.5: untrusted text is rendered by React's escaping only. These rules make the
// alternative a build failure, not a code-review comment.
export default [
  js.configs.recommended,
  {
    files: ['src/**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2023, sourceType: 'module', globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: '18.3' } },
    plugins: { react, 'react-hooks': hooks },
    rules: {
      ...react.configs.recommended.rules,
      ...hooks.configs.recommended.rules,
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
      'react/no-danger': 'error',
      'no-restricted-properties': ['error',
        { property: 'innerHTML', message: 'Never write HTML from data (§14.5).' },
        { property: 'outerHTML', message: 'Never write HTML from data (§14.5).' }],
      'no-restricted-syntax': ['error',
        { selector: "MemberExpression[property.name='innerHTML']", message: 'Never write HTML from data (§14.5).' },
        { selector: "CallExpression[callee.property.name='insertAdjacentHTML']", message: 'Never write HTML from data (§14.5).' }],
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
];
