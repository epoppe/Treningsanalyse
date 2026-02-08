'use client';

import React, { useState, useRef, useEffect } from 'react';
import styled from 'styled-components';

const ChatContainer = styled.div`
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  height: 400px;
  overflow: hidden;
`;

const ChatHeader = styled.div`
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  color: white;
  padding: 1rem 1.25rem;
  font-weight: 600;
  font-size: 1rem;
`;

const MessagesContainer = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
`;

const MessageBubble = styled.div<{ $isUser: boolean }>`
  max-width: 85%;
  padding: 0.75rem 1rem;
  border-radius: 12px;
  font-size: 0.95rem;
  line-height: 1.5;
  align-self: ${(p) => (p.$isUser ? 'flex-end' : 'flex-start')};
  background: ${(p) => (p.$isUser ? '#2563eb' : '#f1f5f9')};
  color: ${(p) => (p.$isUser ? 'white' : '#334155')};
`;

const InputRow = styled.div`
  display: flex;
  gap: 0.5rem;
  padding: 1rem;
  border-top: 1px solid #e2e8f0;
`;

const Input = styled.input`
  flex: 1;
  padding: 0.75rem 1rem;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 0.95rem;

  &:focus {
    outline: none;
    border-color: #2563eb;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
  }
`;

const SendButton = styled.button`
  padding: 0.75rem 1.25rem;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;

  &:hover {
    background: #1d4ed8;
  }

  &:disabled {
    background: #94a3b8;
    cursor: not-allowed;
  }
`;

const EmptyState = styled.div`
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  font-size: 0.9rem;
  text-align: center;
  padding: 2rem;
`;

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ReadinessChatProps {
  selectedDate: string;
  onSendMessage: (message: string, date: string) => Promise<string>;
}

export default function ReadinessChat({ selectedDate, onSendMessage }: ReadinessChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setLoading(true);

    try {
      const response = await onSendMessage(text, selectedDate);
      setMessages((prev) => [...prev, { role: 'assistant', content: response }]);
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string }; status?: number } }).response?.data?.detail
          || `HTTP ${(err as { response?: { status?: number } }).response?.status}`
        : err instanceof Error ? err.message : 'Beklager, det oppstod en feil. Prøv igjen.';
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Feil: ${msg}` },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <ChatContainer>
      <ChatHeader>💬 Spør om readiness for {new Date(selectedDate + 'T12:00:00').toLocaleDateString('nb-NO', { weekday: 'long', day: 'numeric', month: 'long' })}</ChatHeader>
      <MessagesContainer>
        {messages.length === 0 ? (
          <EmptyState>
            Spør f.eks.: «Er jeg klar for trening i dag?», «Hva anbefaler du?», «Hvordan er søvnscore?»
          </EmptyState>
        ) : (
          messages.map((m, i) => (
            <MessageBubble key={i} $isUser={m.role === 'user'}>
              {m.content}
            </MessageBubble>
          ))
        )}
        {loading && (
          <MessageBubble $isUser={false}>
            Tenker...
          </MessageBubble>
        )}
        <div ref={messagesEndRef} />
      </MessagesContainer>
      <InputRow>
        <Input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Skriv spørsmål..."
          disabled={loading}
        />
        <SendButton onClick={handleSend} disabled={loading || !input.trim()}>
          Send
        </SendButton>
      </InputRow>
    </ChatContainer>
  );
}
