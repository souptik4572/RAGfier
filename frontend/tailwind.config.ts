import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#FFFFFF',
        foreground: '#111827',
        primary: {
          DEFAULT: '#3B82F6',
          hover: '#2563EB',
        },
        secondary: {
          DEFAULT: '#10B981',
          hover: '#059669',
        },
        accent: {
          DEFAULT: '#F59E0B',
          hover: '#D97706',
        },
        muted: {
          DEFAULT: '#F3F4F6',
          hover: '#E5E7EB',
        },
        border: '#E5E7EB',
      },
      fontFamily: {
        sans: ['Outfit', 'sans-serif'],
      },
      borderRadius: {
        md: '6px',
        lg: '8px',
      },
      boxShadow: {
        none: 'none',
      },
    },
  },
  plugins: [],
};

export default config;
