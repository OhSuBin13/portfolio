import type { TossAccount } from "./types"

export const formatTossAccountLabel = (account: TossAccount) =>
  `${account.display_name} (${account.account_type})`
