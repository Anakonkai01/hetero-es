import type { ReactNode } from "react";
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { AppStateProvider } from "./AppStateProvider";
import { SessionProvider } from "./SessionProvider";
import { PresentationProvider } from "./presentation";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

interface AppProvidersProps {
  children: ReactNode;
}

export function AppProviders({ children }: AppProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider><PresentationProvider><AppStateProvider>{children}</AppStateProvider></PresentationProvider></SessionProvider>
    </QueryClientProvider>
  );
}
