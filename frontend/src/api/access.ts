import type { AuditEntry, LoginResponse, ModelRegistration, ResourceOverview, Session } from "../types/access";
import { apiGet, apiPost } from "./client";

export const getSession = () => apiGet<Session>("/api/v1/auth/session");
export const login = (input: { username: string; password: string }) => apiPost<LoginResponse>("/api/v1/auth/login", input);
export const logout = () => apiPost<void>("/api/v1/auth/logout");
export const getResourceOverview = () => apiGet<ResourceOverview>("/api/v1/resources");
export const getModels = () => apiGet<ModelRegistration[]>("/api/v1/models");
export const getAudit = () => apiGet<AuditEntry[]>("/api/v1/audit");
