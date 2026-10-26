"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field, FormError, Input } from "@/components/ui/field";
import { errorMessage, fieldErrorsOf } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { safeNextPath } from "@/lib/navigation";

export function LoginForm() {
  const { login, status } = useAuth();
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, router, next]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPending(true);
    setFormError(null);
    setFieldErrors({});
    try {
      await login(email.trim(), password);
      // The effect above navigates once the session is applied.
    } catch (error) {
      setFieldErrors(fieldErrorsOf(error));
      setFormError(errorMessage(error));
      setPending(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <FormError message={formError} />
      <Field label="Work email" error={fieldErrors.email}>
        {(props) => (
          <Input
            {...props}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
          />
        )}
      </Field>
      <Field label="Password" error={fieldErrors.password}>
        {(props) => (
          <Input
            {...props}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        )}
      </Field>
      <Button type="submit" size="lg" className="w-full" loading={pending} disabled={!email || !password}>
        Log in
      </Button>
      <p className="text-center text-sm text-muted-foreground">
        New to Helploom?{" "}
        <Link href="/signup" className="font-medium text-primary hover:underline">
          Create a workspace
        </Link>
      </p>
    </form>
  );
}
