import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { InvitationAccept } from "@/components/auth/invitation-accept";
import { LoadingBlock } from "@/components/ui/states";

export const metadata: Metadata = { title: "Join your team", robots: { index: false, follow: false } };

export default function InvitePage() {
  return (
    <AuthLayout title="Join your team" description="You have been invited to a Helploom workspace.">
      <Suspense fallback={<LoadingBlock />}>
        <InvitationAccept />
      </Suspense>
    </AuthLayout>
  );
}
