import { Dispatch, SetStateAction, useEffect, useState } from "react";

export function usePersistentState<T>(storageKey: string, initialValue: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined") {
      return initialValue;
    }
    const storedValue = window.localStorage.getItem(storageKey);
    if (storedValue === null) {
      return initialValue;
    }
    try {
      return JSON.parse(storedValue) as T;
    } catch {
      return initialValue;
    }
  });

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(value));
  }, [storageKey, value]);

  return [value, setValue];
}
