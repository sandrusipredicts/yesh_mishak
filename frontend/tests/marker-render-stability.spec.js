import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

test('field markers use the field id as their stable React key', () => {
  const mapPageSource = readFileSync('src/pages/MapPage.jsx', 'utf8')

  expect(mapPageSource).toContain('fields.map((field) =>')
  expect(mapPageSource).toContain('key={field.id}')
  expect(mapPageSource).not.toMatch(/key=\{`[^`]*\$\{index\}/)
})
