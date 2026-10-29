import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'cn.smartdocflow.mobile',
  appName: '文枢智动',
  webDir: 'dist-native',
  server: {
    // Capacitor Android defaults to https://localhost. When backend endpoint is
    // plain http (for example FRP on :82), WebView can throw `Failed to fetch`.
    androidScheme: 'http',
  },
  android: {
    // Keep mixed-content explicitly enabled for WebView compatibility across
    // Android variants when backend endpoint remains http.
    allowMixedContent: true,
  },
};

export default config;
