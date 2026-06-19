import { apiPost } from './client'

export interface UploadImageResult {
  url: string
  filename: string
  size: number
  mime?: string | null
}

/**
 * Upload a single image to the backend. The returned `url` is a public static
 * path (e.g. `/uploads/<uid>/<snowflake>.png`) meant to be embedded in note
 * Markdown content.
 *
 * No Content-Type header is set explicitly: passing a FormData body lets the
 * browser generate the multipart boundary. Hard-coding `multipart/form-data`
 * omits the boundary, which the axios `fetch` adapter would send as-is → 422.
 */
export function uploadImage(file: File | Blob) {
  const form = new FormData()
  form.append('file', file)
  return apiPost<UploadImageResult>('/v1/upload/image', form, {
    // Images may be large; allow more than the default 20s.
    timeout: 60000,
  })
}
