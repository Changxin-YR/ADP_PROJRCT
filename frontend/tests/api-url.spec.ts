import { describe, expect, it } from 'vitest'
import { apiUrl } from '../src/layers/common/api/base'

describe('apiUrl', () => {
  it('joins a configured server URL with API paths', () => {
    expect(apiUrl('/api/v1/auth/me', 'https://adp.example.com/')).toBe('https://adp.example.com/api/v1/auth/me')
    expect(apiUrl('https://other.example.com/status', 'https://adp.example.com')).toBe('https://other.example.com/status')
  })
})
