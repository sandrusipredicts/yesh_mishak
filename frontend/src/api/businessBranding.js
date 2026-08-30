import { api } from './client'

export async function getBusinessBranding() {
  const response = await api.get('/branding')
  return response.data
}

export async function getAdminBusinessBranding() {
  const response = await api.get('/admin/settings/business-branding')
  return response.data
}

export async function updateAdminBusinessBranding(businessName) {
  const response = await api.patch('/admin/settings/business-branding', {
    business_name: businessName,
  })
  return response.data
}
