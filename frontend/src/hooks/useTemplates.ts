import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost } from "../api/client";
import { useScopeKey } from "../app/session";
import type { Template, TemplateConfig } from "../lib/templates";

export function useTemplates() {
  const scope = useScopeKey();
  return useQuery({ queryKey: ["experiment-templates", ...scope], queryFn: () => apiGet<Template[]>("/api/v1/experiment-templates"), enabled: scope.every(Boolean), retry: 1 });
}

export function useTemplateMutations() {
  const cache = useQueryClient();
  const refresh = () => cache.invalidateQueries({ queryKey: ["experiment-templates"] });
  const create = useMutation({ mutationFn: (input: { name: string; config: TemplateConfig }) => apiPost<Template>("/api/v1/experiment-templates", input), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => apiDelete(`/api/v1/experiment-templates/${encodeURIComponent(id)}`), onSuccess: refresh });
  return { create, remove };
}
