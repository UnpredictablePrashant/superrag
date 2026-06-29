import nextVitals from "eslint-config-next/core-web-vitals";

export default [
  { ignores: [".next/**", "next-env.d.ts"] },
  ...nextVitals,
  {
    rules: {
      "react-hooks/set-state-in-effect": "off",
      "import/no-anonymous-default-export": "off",
    },
  },
];
