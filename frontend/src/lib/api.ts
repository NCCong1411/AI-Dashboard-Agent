export type AuthUser = {
  username: string;
  role: "builder" | "viewer";
  scope_profile: "ALL" | "CA" | "TX";
};

export async function login(username: string, password: string): Promise<AuthUser> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({username, password}),
  });
  if (!response.ok) {
    throw new Error(response.status === 401 ? "Sai tên đăng nhập hoặc mật khẩu." : "Không thể đăng nhập.");
  }
  return (await response.json()) as AuthUser;
}

export async function currentUser(): Promise<AuthUser | null> {
  const response = await fetch("/api/auth/me", {cache: "no-store", credentials: "same-origin"});
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Không thể tải phiên đăng nhập.");
  return (await response.json()) as AuthUser;
}

export async function logout(): Promise<void> {
  const response = await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error("Không thể đăng xuất.");
}
