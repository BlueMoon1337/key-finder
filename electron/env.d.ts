// Text files bundled into the main process by esbuild (scripts/build-electron.mjs).
declare module '*.pem' {
  const text: string
  export default text
}
