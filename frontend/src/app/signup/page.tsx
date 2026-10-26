import type { Metadata } from "next";

import { AuthLayout } from "@/components/auth/auth-layout";
import { SignupForm } from "@/components/auth/signup-form";

export const metadata: Metadata = { title: "Create your workspace" };

export default function SignupPage() {
  return (
    <AuthLayout
      title="Create your workspace"
      description="Start on the Free plan and upgrade when you need more. No card needed."
    >
      <SignupForm />
    </AuthLayout>
  );
}
