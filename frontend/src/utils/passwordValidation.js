export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 128

export function getPasswordValidationError(password, t) {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return t('auth.passwordTooShort', { count: PASSWORD_MIN_LENGTH })
  }

  if (password.length > PASSWORD_MAX_LENGTH) {
    return t('auth.passwordTooLong', { count: PASSWORD_MAX_LENGTH })
  }

  return ''
}
