import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.yeshmishak.app',
  appName: 'Yesh Mishak',
  webDir: 'dist',
  android: {
    // Capacitor debug logging serializes native plugin arguments and results,
    // including SocialLogin credentials and SecureStorage values, to logcat.
    loggingBehavior: 'none',
  },
  plugins: {
    // Only the Google provider is approved (NA-1 selection); disabling the
    // rest keeps their native SDKs (e.g. Facebook) out of the APK.
    SocialLogin: {
      providers: {
        google: true,
        facebook: false,
        apple: false,
        twitter: false,
      },
    },
  },
};

export default config;
