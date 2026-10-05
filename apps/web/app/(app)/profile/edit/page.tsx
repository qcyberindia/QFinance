"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import { useSession } from "@/lib/session";
import type { MyProfile } from "@/lib/types";
import { ErrorState } from "@/components/states";
import s from "@/components/profile/profile.module.css";

const NAME_MAX = 80;
const BIO_MAX = 500;
const USERNAME_RE = /^[A-Za-z0-9_]{3,30}$/;

type Form = { name: string; username: string; bio: string; experience_level: string };

/** PATCH /users/me/profile — the session's own profile only. Email is not
 * editable here. No avatar upload: the schema deliberately has no avatar
 * column (OD-21), so avatars stay generated from the username. */
export default function EditProfilePage() {
  const { refresh } = useSession();
  const [original, setOriginal] = useState<Form | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  const load = useCallback(async () => {
    setLoadError(false);
    try {
      const me = await api.get<MyProfile>("/users/me/profile");
      const f = { name: me.name, username: me.username, bio: me.bio ?? "", experience_level: me.experience_level ?? "" };
      setOriginal(f);
      setForm(f);
    } catch {
      setLoadError(true);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loadError) return <div className="mt-4"><ErrorState message="We couldn't load your profile. Try again." onRetry={load} /></div>;
  if (!form || !original) return <div className="qf-skeleton mt-4" style={{ height: 320 }} aria-busy="true" aria-label="Loading profile" />;

  const set = (k: keyof Form, v: string) => { setForm({ ...form, [k]: v }); setStatus("idle"); };
  const clientErrors: Record<string, string> = {};
  if (!form.name.trim() || form.name.trim().length > NAME_MAX) clientErrors.name = `Name must be 1–${NAME_MAX} characters.`;
  if (!USERNAME_RE.test(form.username.trim())) clientErrors.username = "3–30 letters, numbers or underscores.";
  if (form.bio.length > BIO_MAX) clientErrors.bio = `Bio must be at most ${BIO_MAX} characters.`;
  const shown = { ...clientErrors, ...errors };
  const dirty = (Object.keys(form) as (keyof Form)[]).some((k) => form[k] !== original[k]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form || !original || Object.keys(clientErrors).length) return;
    const changes: Record<string, string | null> = {};
    (Object.keys(form) as (keyof Form)[]).forEach((k) => {
      if (form[k] !== original[k]) changes[k] = k === "experience_level" ? (form[k] || null) : form[k].trim();
    });
    setStatus("saving");
    setErrors({});
    try {
      const me = await api.patch<MyProfile>("/users/me/profile", changes);
      const f = { name: me.name, username: me.username, bio: me.bio ?? "", experience_level: me.experience_level ?? "" };
      setOriginal(f);
      setForm(f);
      setStatus("saved");
      if ("username" in changes) await refresh();
    } catch (err) {
      setStatus("error");
      if (err instanceof ApiError && err.fields) setErrors(err.fields);
    }
  }

  const field = (id: keyof Form) => ({
    id: `pf-${id}`,
    "aria-invalid": shown[id] ? true : undefined,
    "aria-describedby": `pf-${id}-hint${shown[id] ? ` pf-${id}-err` : ""}`,
  });

  return (
    <form className={`${s.form} mt-4`} onSubmit={save} noValidate>
      <div>
        <label className="qf-label" htmlFor="pf-username">Username</label>
        <input {...field("username")} className="qf-input" value={form.username} autoComplete="username"
          onChange={(e) => set("username", e.target.value)} />
        <p id="pf-username-hint" className={s.hint}>Your public identity in Community. Changing it changes your profile link.</p>
        {shown.username && <p id="pf-username-err" className={s.fieldError} role="alert">{shown.username}</p>}
      </div>

      <div>
        <label className="qf-label" htmlFor="pf-bio">Bio</label>
        <textarea {...field("bio")} className="qf-input" rows={4} value={form.bio} maxLength={BIO_MAX + 50}
          placeholder="What do you research? What kind of investor are you?"
          onChange={(e) => set("bio", e.target.value)} />
        <p className={s.counter} aria-live="polite">{form.bio.length}/{BIO_MAX}</p>
        <p id="pf-bio-hint" className={s.hint}>Public. Don&apos;t include personal contact details.</p>
        {shown.bio && <p id="pf-bio-err" className={s.fieldError} role="alert">{shown.bio}</p>}
      </div>

      <div>
        <label className="qf-label" htmlFor="pf-name">Name</label>
        <input {...field("name")} className="qf-input" value={form.name} autoComplete="name"
          onChange={(e) => set("name", e.target.value)} />
        <p id="pf-name-hint" className={s.hint}>Private — never shown to other members.</p>
        {shown.name && <p id="pf-name-err" className={s.fieldError} role="alert">{shown.name}</p>}
      </div>

      <div>
        <label className="qf-label" htmlFor="pf-experience_level">Investing experience</label>
        <select {...field("experience_level")} className="qf-input" value={form.experience_level}
          onChange={(e) => set("experience_level", e.target.value)}>
          <option value="">Prefer not to say</option>
          <option value="beginner">Beginner</option>
          <option value="intermediate">Intermediate</option>
          <option value="advanced">Advanced</option>
        </select>
        <p id="pf-experience_level-hint" className={s.hint}>Private — helps tailor explanations; never shown publicly.</p>
        {shown.experience_level && <p id="pf-experience_level-err" className={s.fieldError} role="alert">{shown.experience_level}</p>}
      </div>

      <div className={s.actions}>
        <button type="submit" className="qf-btn-primary" aria-busy={status === "saving"}
          disabled={!dirty || status === "saving" || Object.keys(clientErrors).length > 0}>
          {status === "saving" ? "Saving…" : "Save changes"}
        </button>
        {dirty && status !== "saving" && (
          <button type="button" className="qf-btn-ghost" onClick={() => { setForm(original); setErrors({}); setStatus("idle"); }}>
            Discard
          </button>
        )}
        <span aria-live="polite">
          {status === "saved" && <span className={s.ok}>✓ Profile saved</span>}
          {status === "error" && !Object.keys(errors).length && <span className={s.fieldError}>Couldn&apos;t save. Try again.</span>}
        </span>
      </div>
      <p className={s.hint}>Your email address can&apos;t be changed here. There is no profile photo upload — your avatar is generated from your username.</p>
    </form>
  );
}
