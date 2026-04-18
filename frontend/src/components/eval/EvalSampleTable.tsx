'use client';

import { Fragment, useState } from 'react';
import { ChevronDown, ChevronRight, CheckCircle2, XCircle } from 'lucide-react';
import type { EvalSampleResult } from '@/lib/api/eval';
import { cn, truncate } from '@/lib/utils';

interface EvalSampleTableProps {
  samples: EvalSampleResult[];
}

function ScoreCell({ value }: { value: number | null | undefined }) {
  if (typeof value !== 'number') {
    return <span className="text-gray-400 font-mono text-xs">—</span>;
  }
  const tone =
    value >= 0.7
      ? 'text-[#10B981]'
      : value >= 0.45
      ? 'text-[#F59E0B]'
      : 'text-red-500';
  return <span className={cn('font-mono text-xs font-semibold', tone)}>{value.toFixed(2)}</span>;
}

function formatReason(reason: unknown): string {
  if (typeof reason === 'string') return reason;
  if (reason && typeof reason === 'object') {
    try {
      return JSON.stringify(reason);
    } catch {
      return String(reason);
    }
  }
  return String(reason);
}

export function EvalSampleTable({ samples }: EvalSampleTableProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="bg-white rounded-lg overflow-hidden">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-[#111827] text-white">
            <th className="w-8 px-3 py-3" />
            <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
              Question
            </th>
            <th className="text-left text-xs font-semibold uppercase tracking-wider px-4 py-3">
              Answer
            </th>
            <th className="text-right text-xs font-semibold uppercase tracking-wider px-3 py-3">
              Faith
            </th>
            <th className="text-right text-xs font-semibold uppercase tracking-wider px-3 py-3">
              Answer
            </th>
            <th className="text-right text-xs font-semibold uppercase tracking-wider px-3 py-3">
              Citation
            </th>
            <th className="text-center text-xs font-semibold uppercase tracking-wider px-3 py-3">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {samples.map((sample, idx) => {
            const isOpen = expanded.has(sample.sample_id);
            const rowBg = idx % 2 === 0 ? 'bg-white' : 'bg-[#F9FAFB]';
            return (
              <Fragment key={sample.sample_id}>
                <tr
                  className={cn(
                    rowBg,
                    'cursor-pointer hover:bg-[#F3F4F6] transition-colors duration-150'
                  )}
                  onClick={() => toggle(sample.sample_id)}
                >
                  <td className="px-3 py-3 align-top">
                    {isOpen ? (
                      <ChevronDown className="h-4 w-4 text-gray-400" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-gray-400" />
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-[#111827] align-top max-w-md">
                    {truncate(sample.user_input, 120)}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 align-top max-w-md">
                    {truncate(sample.response, 120)}
                  </td>
                  <td className="px-3 py-3 text-right align-top">
                    <ScoreCell value={sample.scores.faithfulness} />
                  </td>
                  <td className="px-3 py-3 text-right align-top">
                    <ScoreCell value={sample.scores.answer_relevancy} />
                  </td>
                  <td className="px-3 py-3 text-right align-top">
                    <ScoreCell value={sample.scores.citation_coverage} />
                  </td>
                  <td className="px-3 py-3 text-center align-top">
                    {sample.passed === true ? (
                      <CheckCircle2 className="h-4 w-4 text-[#10B981] inline" />
                    ) : sample.passed === false ? (
                      <XCircle className="h-4 w-4 text-red-500 inline" />
                    ) : (
                      <span className="text-gray-400 text-xs">—</span>
                    )}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="bg-[#F3F4F6]">
                    <td />
                    <td colSpan={6} className="px-4 py-4">
                      <div className="space-y-3 text-sm">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">
                            Question
                          </p>
                          <p className="text-[#111827] whitespace-pre-wrap">
                            {sample.user_input}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">
                            Answer
                          </p>
                          <p className="text-[#111827] whitespace-pre-wrap">
                            {sample.response}
                          </p>
                        </div>
                        {sample.category && (
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">
                              Category
                            </p>
                            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-white text-[#111827]">
                              {sample.category}
                            </span>
                          </div>
                        )}
                        {sample.failure_reasons.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-wider text-red-600 mb-1">
                              Failure reasons
                            </p>
                            <ul className="list-disc pl-5 space-y-1 text-xs text-red-700">
                              {sample.failure_reasons.map((r, i) => (
                                <li key={i}>{formatReason(r)}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
