import { LoginForm } from '@/components/auth/LoginForm';

export default function LoginPage() {
  return (
    <div className="flex h-screen w-full">
      {/* Left decorative panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-[#3B82F6] relative overflow-hidden flex-col items-center justify-center">
        {/* Decorative geometric circles */}
        <div className="absolute top-[-80px] left-[-80px] w-[400px] h-[400px] rounded-full bg-white opacity-5" />
        <div className="absolute bottom-[-120px] right-[-100px] w-[500px] h-[500px] rounded-full bg-white opacity-5" />
        <div className="absolute top-[30%] right-[-60px] w-[250px] h-[250px] rounded-full bg-white opacity-5" />
        <div className="absolute bottom-[20%] left-[10%] w-[180px] h-[180px] rounded-full bg-white opacity-5" />

        <div className="relative z-10 text-center px-8">
          <h1 className="text-5xl font-extrabold text-white mb-4">
            RAGfier
            <span className="text-[#F59E0B]">.</span>
          </h1>
          <p className="text-white/80 text-xl font-medium max-w-sm">
            RAG-as-a-Service. Connect your documents, power your AI.
          </p>
        </div>
      </div>

      {/* Right login form */}
      <div className="flex flex-1 items-center justify-center px-8 bg-white">
        <div className="w-full max-w-md">
          <div className="mb-8">
            <div className="lg:hidden mb-6">
              <span className="text-3xl font-extrabold text-[#111827]">
                RAGfier<span className="text-[#3B82F6]">.</span>
              </span>
            </div>
            <h2 className="text-3xl font-extrabold text-[#111827] tracking-tight">
              Welcome back
            </h2>
            <p className="mt-2 text-gray-500 font-medium">
              Sign in to your account to continue
            </p>
          </div>
          <LoginForm />
        </div>
      </div>
    </div>
  );
}
