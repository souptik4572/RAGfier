"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { getIntegration } from "@/lib/api/integrations";
import { PageHeader } from "@/components/layout/PageHeader";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";

interface PlaygroundPageProps {
	params: Promise<{ id: string }>;
}

export default function PlaygroundPage({ params }: PlaygroundPageProps) {
	const { id } = use(params);

	const { data: integration } = useQuery({
		queryKey: ["integration", id],
		queryFn: () => getIntegration(id),
	});

	return (
		<div className="flex flex-col h-full">
			<PageHeader
				title={integration?.name ?? "Playground"}
				subtitle="Test your RAG pipeline with queries"
			/>
			<ErrorBoundary label="The chat session ran into an error">
				<ChatWindow integrationId={id} />
			</ErrorBoundary>
		</div>
	);
}
