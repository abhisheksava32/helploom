"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field, FormError, Input } from "@/components/ui/field";
import { errorMessage, fieldErrorsOf, isApiError } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";

const MIN_PASSWORD = 10;

export function SignupForm() {
  const { signup, status } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", organization_name: "", email: "", password: "" });
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (status === "authenticated") router.replace("/app");
  }, [status, router]);

  const update = (field: keyof typeof form) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [field]: event.target.value }));

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const local: Record<string, string> = {};
    if (form.organization_name.trim().length < 2) local.organization_name = "Enter your business name.";
    if (form.password.length < MIN_PASSWORD) local.password = `Use at least ${MIN_PASSWORD} characters.`;
    setFieldErrors(local);
    if (Object.keys(local).length > 0) return;

    setPending(true);
    setFormError(null);
    try {
      await signup({
        full_name: form.full_name.trim(),
        organization_name: form.organization_name.trim(),
        email: form.email.trim(),
        password: form.password,
      });
    } catch (error) {
      setFieldErrors(fieldErrorsOf(error));
      setFormError(isApiError(error, "validation_error") ? "Please fix the highlighted fields." : errorMessage(error));
      setPending(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      <FormError message={formError} />
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Your name" error={fieldErrors.full_name} optional>
          {(props) => (
            <Input {...props} autoComplete="name" value={form.full_name} onChange={update("full_name")} />
          )}
        </Field>
        <Field label="Business name" error={fieldErrors.organization_name}>
          {(props) => (
            <Input
              {...props}
              autoComplete="organization"
              required
              value={form.organization_name}
              onChange={update("organization_name")}
              placeholder="Northwind Outfitters"
            />
          )}
        </Field>
      </div>
      <Field label="Work email" error={fieldErrors.email}>
        {(props) => (
          <Input
            {...props}
            type="email"
            autoComplete="email"
            required
            value={form.email}
            onChange={update("email")}
            placeholder="you@company.com"
          />
        )}
      </Field>
      <Field
        label="Password"
        error={fieldErrors.password}
        hint={`At least ${MIN_PASSWORD} characters. A short phrase is easier to remember.`}
      >
        {(props) => (
          <Input
            {...props}
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD}
            value={form.password}
            onChange={update("password")}
          />
        )}
      </Field>
      <Button type="submit" size="lg" className="w-full" loading={pending}>
        Create workspace
      </Button>
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Log in
        </Link>
      </p>
    </form>
  );
}
