import apiClient from "./client";
import type { AuthTokens, User } from "@/lib/types";

export async function googleLogin(
  code: string,
  redirectUri: string
): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>("/auth/google", {
    code,
    redirect_uri: redirectUri,
  });
  return data;
}

export async function refreshToken(token: string): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>("/auth/refresh", {
    refresh_token: token,
  });
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}

export async function getMe(): Promise<User> {
  const { data } = await apiClient.get<User>("/auth/me");
  return data;
}
