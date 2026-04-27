import { SignIn } from "@clerk/nextjs";

export default function Page() {
  return (
    <main className="min-h-dvh flex items-center justify-center p-6">
      <SignIn />
    </main>
  );
}
