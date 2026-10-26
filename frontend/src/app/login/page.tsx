import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { LoginForm } from "@/components/auth/login-form";
import { LoadingBlock } from "@/components/ui/states";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <AuthLayout title="Welcome back" description="Log in to manage your help desk.">
      <Suspense fallback={<LoadingBlock />}>
        <LoginForm />
      </Suspense>
    </AuthLayout>
  );
}
