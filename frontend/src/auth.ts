import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim() ?? "";
const supabasePublishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim() ?? "";
const isConfiguredValue = (value: string) =>
  Boolean(value) && !/your-project-id|your-supabase|replace-with|placeholder/i.test(value);

export const supabaseConfigured = isConfiguredValue(supabaseUrl) && isConfiguredValue(supabasePublishableKey);
const supabase: SupabaseClient | null = supabaseConfigured
  ? createClient(supabaseUrl, supabasePublishableKey)
  : null;

function requireClient(): SupabaseClient {
  if (!supabase) {
    throw new Error("Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in frontend/.env.local.");
  }
  return supabase;
}

export const authApi = {
  getSession: async (): Promise<Session | null> => {
    const { data, error } = await requireClient().auth.getSession();
    if (error) throw error;
    return data.session;
  },

  onAuthStateChange: (callback: (session: Session | null) => void) => {
    const { data } = requireClient().auth.onAuthStateChange((_event, session) => callback(session));
    return () => data.subscription.unsubscribe();
  },

  signUp: async (email: string, password: string, fullName: string): Promise<Session | null> => {
    const { data, error } = await requireClient().auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
        emailRedirectTo: window.location.origin,
      },
    });
    if (error) throw error;
    return data.session;
  },

  signIn: async (email: string, password: string): Promise<Session> => {
    const { data, error } = await requireClient().auth.signInWithPassword({ email, password });
    if (error) throw error;
    if (!data.session) throw new Error("Sign-in succeeded without an active session. Please try again.");
    return data.session;
  },

  signOut: async (): Promise<void> => {
    const { error } = await requireClient().auth.signOut();
    if (error) throw error;
  },
};

export type { Session as AuthSession };
