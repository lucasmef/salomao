import { useSyncExternalStore } from "react";

import { getNetworkActivityCount, subscribeToNetworkActivity } from "../lib/api";

export function useNetworkActivityCount() {
  return useSyncExternalStore(subscribeToNetworkActivity, getNetworkActivityCount, () => 0);
}
