/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Catppuccin Mocha inspired palette
        base: '#1e1e2e',
        surface: '#313244',
        overlay: '#45475a',
        muted: '#6c7086',
        text: '#cdd6f4',
        subtext: '#a6adc8',
        lavender: '#b4befe',
        blue: '#89b4fa',
        sapphire: '#74c7ec',
        sky: '#89dceb',
        teal: '#94e2d5',
        green: '#a6e3a1',
        yellow: '#f9e2af',
        peach: '#fab387',
        maroon: '#eba0ac',
        red: '#f38ba8',
        mauve: '#cba6f7',
        pink: '#f5c2e7',
        flamingo: '#f2cdcd',
        rosewater: '#f5e0dc',
      },
      fontFamily: {
        sans: ['JetBrains Mono', 'SF Mono', 'Menlo', 'monospace'],
        display: ['Cal Sans', 'Inter', 'sans-serif'],
      },
      animation: {
        'gradient': 'gradient 8s linear infinite',
        'float': 'float 6s ease-in-out infinite',
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        gradient: {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-20px)' },
        },
        glow: {
          '0%': { boxShadow: '0 0 20px rgba(180, 190, 254, 0.3)' },
          '100%': { boxShadow: '0 0 40px rgba(180, 190, 254, 0.6)' },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        'mesh': `radial-gradient(at 40% 20%, rgba(180, 190, 254, 0.15) 0px, transparent 50%),
                 radial-gradient(at 80% 0%, rgba(137, 180, 250, 0.1) 0px, transparent 50%),
                 radial-gradient(at 0% 50%, rgba(203, 166, 247, 0.1) 0px, transparent 50%),
                 radial-gradient(at 80% 50%, rgba(148, 226, 213, 0.1) 0px, transparent 50%),
                 radial-gradient(at 0% 100%, rgba(245, 194, 231, 0.1) 0px, transparent 50%)`,
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
};
