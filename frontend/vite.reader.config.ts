import { createHash } from 'node:crypto'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Desktop browsers cannot import ES modules from an extracted file:// document.
// Bundle the same reader and its dynamic imports as one local classic script.
// Media stays as separate verified files: no base64 copies of large PNG/WAV assets.
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'taleprism-reader-build-integrity',
      enforce: 'post',
      generateBundle: {
        order: 'post',
        handler(_, bundle) {
          const files: Record<string, string> = {}
          for (const name of ['reader.js', 'reader.css']) {
            const item = bundle[name]
            if (!item) this.error('Missing portable reader bundle: ' + name)
            const raw = item.type === 'chunk' ? item.code : item.source
            if (!raw.length) this.error('Empty portable reader bundle: ' + name)
            files[name] = createHash('sha256').update(raw).digest('hex')
          }
          this.emitFile({
            type: 'asset',
            fileName: 'runtime-checksums.json',
            source: JSON.stringify(files),
          })
        },
      },
    },
  ],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: 'dist/reader',
    lib: {
      entry: 'src/portableReader.tsx',
      name: 'TaleprismReader',
      formats: ['iife'],
      fileName: () => 'reader.js',
      cssFileName: 'reader',
    },
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
})
