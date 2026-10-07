import { useQueryClient } from "@tanstack/react-query";

import type { S } from "../../api/client";

/** Las modificaciones del perfil devuelven el perfil completo: se guarda como fuente de verdad. */
export function useSaveProfile() {
  const queryClient = useQueryClient();
  return (profile: S["ProfileOut"]) => {
    queryClient.setQueryData(["profile"], profile);
    queryClient.invalidateQueries({ queryKey: ["me"] });
  };
}
