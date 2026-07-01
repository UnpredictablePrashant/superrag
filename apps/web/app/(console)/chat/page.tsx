"use client";

import { AskWorkspace } from "@/components/ask-workspace";
import { ErrorBox } from "@/components/error-box";
import {
  addTeamChatParticipants,
  createTeamChatChannel,
  createTeamChatDirect,
  createTeamChatMessage,
  deleteTeamChatMessage,
  getMe,
  listMembers,
  listTeamChatConversations,
  listTeamChatMessages,
  markTeamChatRead,
  updateTeamChatPresence,
  updateTeamChatMessage,
  type ChatPresenceStatus,
  type TeamChatConversation,
  type TeamChatMessage,
  type TeamChatParticipant,
} from "@/lib/api";
import { Badge, Button, Input, Label, Panel, Select, Textarea, cn } from "@rag-console/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AtSign,
  Bot,
  Check,
  Hash,
  MessageSquare,
  MessageSquarePlus,
  Pencil,
  Plus,
  Search,
  Send,
  Trash2,
  Users,
  X,
} from "lucide-react";
import * as React from "react";

type MemberOption = Awaited<ReturnType<typeof listMembers>>[number];

const presenceOptions: Array<{ value: ChatPresenceStatus; label: string }> = [
  { value: "online", label: "Online" },
  { value: "busy", label: "Busy" },
  { value: "away", label: "Away" },
  { value: "do_not_disturb", label: "Do not disturb" },
  { value: "offline", label: "Unavailable" },
];

export default function TeamChatPage() {
  const queryClient = useQueryClient();
  const [chatMode, setChatMode] = React.useState<"people" | "ai">("people");
  const [activeConversationId, setActiveConversationId] = React.useState("");
  const [messageText, setMessageText] = React.useState("");
  const [channelName, setChannelName] = React.useState("");
  const [channelDescription, setChannelDescription] = React.useState("");
  const [selectedChannelMembers, setSelectedChannelMembers] = React.useState<string[]>([]);
  const [directUserId, setDirectUserId] = React.useState("");
  const [addUserId, setAddUserId] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [editingMessageId, setEditingMessageId] = React.useState("");
  const [editingContent, setEditingContent] = React.useState("");
  const [presenceStatus, setPresenceStatus] = React.useState<ChatPresenceStatus>("online");
  const [presenceMessage, setPresenceMessage] = React.useState("");
  const [error, setError] = React.useState("");

  const me = useQuery({ queryKey: ["me"], queryFn: getMe });
  const members = useQuery({ queryKey: ["members"], queryFn: listMembers });
  const conversations = useQuery({
    queryKey: ["team-chat-conversations"],
    queryFn: listTeamChatConversations,
    refetchInterval: 5000,
  });
  const activeConversation = conversations.data?.find((conversation) => conversation.id === activeConversationId);
  const messages = useQuery({
    queryKey: ["team-chat-messages", activeConversationId],
    enabled: Boolean(activeConversationId),
    queryFn: () => listTeamChatMessages(activeConversationId),
    refetchInterval: 3000,
  });

  React.useEffect(() => {
    if (new URLSearchParams(window.location.search).get("mode") === "ai") {
      setChatMode("ai");
    }
  }, []);

  React.useEffect(() => {
    if (!activeConversationId && conversations.data?.[0]) {
      setActiveConversationId(conversations.data[0].id);
    }
  }, [activeConversationId, conversations.data]);

  React.useEffect(() => {
    if (!activeConversationId || !activeConversation?.unread_count) return;
    markTeamChatRead(activeConversationId)
      .then(() => queryClient.invalidateQueries({ queryKey: ["team-chat-conversations"] }))
      .catch(() => undefined);
  }, [activeConversation?.unread_count, activeConversationId, queryClient]);

  const activeMembers = React.useMemo(
    () => (members.data ?? []).filter((member) => member.status === "active"),
    [members.data],
  );
  const currentMember = activeMembers.find((member) => member.user_id === me.data?.user?.id);

  React.useEffect(() => {
    if (!currentMember) return;
    setPresenceStatus(currentMember.chat_status);
    setPresenceMessage(currentMember.status_message ?? "");
  }, [currentMember?.chat_status, currentMember?.status_message, currentMember]);

  const presenceMutation = useMutation({
    mutationFn: () => updateTeamChatPresence(presenceStatus, presenceMessage),
    onSuccess: () => {
      setError("");
      queryClient.invalidateQueries({ queryKey: ["members"] });
      queryClient.invalidateQueries({ queryKey: ["team-chat-conversations"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not update status."),
  });

  const channelMutation = useMutation({
    mutationFn: () =>
      createTeamChatChannel({
        name: channelName,
        description: channelDescription || undefined,
        member_user_ids: selectedChannelMembers,
      }),
    onSuccess: (conversation) => {
      setActiveConversationId(conversation.id);
      setChannelName("");
      setChannelDescription("");
      setSelectedChannelMembers([]);
      setError("");
      queryClient.invalidateQueries({ queryKey: ["team-chat-conversations"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not create channel."),
  });

  const directMutation = useMutation({
    mutationFn: createTeamChatDirect,
    onSuccess: (conversation) => {
      setActiveConversationId(conversation.id);
      setDirectUserId("");
      setError("");
      queryClient.invalidateQueries({ queryKey: ["team-chat-conversations"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not start direct message."),
  });

  const addParticipantMutation = useMutation({
    mutationFn: () => addTeamChatParticipants(activeConversationId, [addUserId]),
    onSuccess: () => {
      setAddUserId("");
      setError("");
      queryClient.invalidateQueries({ queryKey: ["team-chat-conversations"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not add member."),
  });

  async function sendMessage() {
    if (!activeConversationId || !messageText.trim()) return;
    setError("");
    const optimisticText = messageText;
    setMessageText("");
    try {
      await createTeamChatMessage(activeConversationId, optimisticText);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["team-chat-messages", activeConversationId] }),
        queryClient.invalidateQueries({ queryKey: ["team-chat-conversations"] }),
      ]);
    } catch (err) {
      setMessageText(optimisticText);
      setError(err instanceof Error ? err.message : "Could not send message.");
    }
  }

  async function saveEdit(message: TeamChatMessage) {
    if (!editingContent.trim()) return;
    setError("");
    try {
      await updateTeamChatMessage(message.conversation_id, message.id, editingContent);
      setEditingMessageId("");
      setEditingContent("");
      queryClient.invalidateQueries({ queryKey: ["team-chat-messages", activeConversationId] });
      queryClient.invalidateQueries({ queryKey: ["team-chat-conversations"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update message.");
    }
  }

  async function deleteMessage(message: TeamChatMessage) {
    setError("");
    try {
      await deleteTeamChatMessage(message.conversation_id, message.id);
      queryClient.invalidateQueries({ queryKey: ["team-chat-messages", activeConversationId] });
      queryClient.invalidateQueries({ queryKey: ["team-chat-conversations"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete message.");
    }
  }

  const currentUserId = me.data?.user?.id ?? "";
  const filteredConversations = (conversations.data ?? []).filter((conversation) =>
    conversationDisplayName(conversation, currentUserId).toLowerCase().includes(search.toLowerCase()),
  );
  const channels = filteredConversations.filter((conversation) => conversation.kind === "channel");
  const directs = filteredConversations.filter((conversation) => conversation.kind === "direct");
  const addableMembers = activeMembers.filter(
    (member) => !activeConversation?.participants.some((participant) => participant.user_id === member.user_id),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col justify-between gap-3 rounded-md border border-zinc-200 bg-white px-4 py-3 shadow-sm sm:flex-row sm:items-center">
        <div>
          <h2 className="text-xl font-semibold text-zinc-950">Chat</h2>
          <p className="text-sm text-zinc-500">Message teammates or switch to the company knowledge assistant.</p>
        </div>
        <div className="flex flex-col gap-2 sm:items-end">
          <div className="inline-flex rounded-md border border-zinc-200 bg-zinc-50 p-1">
            <button
              className={cn(
                "inline-flex h-9 items-center gap-2 rounded px-3 text-sm font-medium transition",
                chatMode === "people" ? "bg-white text-[#083d59] shadow-sm" : "text-zinc-600 hover:text-zinc-950",
              )}
              onClick={() => setChatMode("people")}
            >
              <MessageSquare className="h-4 w-4" aria-hidden />
              People
            </button>
            <button
              className={cn(
                "inline-flex h-9 items-center gap-2 rounded px-3 text-sm font-medium transition",
                chatMode === "ai" ? "bg-white text-[#083d59] shadow-sm" : "text-zinc-600 hover:text-zinc-950",
              )}
              onClick={() => setChatMode("ai")}
            >
              <Bot className="h-4 w-4" aria-hidden />
              AI assistant
            </button>
          </div>
          {chatMode === "people" ? (
            <div className="flex flex-wrap items-center justify-end gap-2">
              <span className="text-xs font-medium text-zinc-500">My status</span>
              <Select
                className="h-9 w-40"
                value={presenceStatus}
                onChange={(event) => setPresenceStatus(event.target.value as ChatPresenceStatus)}
              >
                {presenceOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
              <Input
                className="h-9 w-48"
                maxLength={160}
                placeholder="Status message"
                value={presenceMessage}
                onChange={(event) => setPresenceMessage(event.target.value)}
              />
              <Button size="sm" disabled={presenceMutation.isPending} onClick={() => presenceMutation.mutate()}>
                Save
              </Button>
            </div>
          ) : null}
        </div>
      </div>
      {chatMode === "ai" ? (
        <AskWorkspace compact />
      ) : (
    <div className="grid h-[calc(100vh-176px)] min-h-[680px] gap-4 xl:grid-cols-[320px_1fr_340px]">
      <Panel className="flex min-h-0 flex-col overflow-hidden">
        <div className="border-b border-zinc-200 p-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-zinc-400" aria-hidden />
            <Input
              className="pl-9"
              placeholder="Search conversations"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-auto p-3">
          <ConversationGroup
            conversations={channels}
            currentUserId={currentUserId}
            icon="channel"
            label="Channels"
            selectedId={activeConversationId}
            onSelect={setActiveConversationId}
          />
          <ConversationGroup
            conversations={directs}
            currentUserId={currentUserId}
            icon="direct"
            label="Direct messages"
            selectedId={activeConversationId}
            onSelect={setActiveConversationId}
          />
        </div>
        <div className="border-t border-zinc-200 p-4">
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="new-channel">New channel</Label>
              <Input
                id="new-channel"
                placeholder="project-updates"
                value={channelName}
                onChange={(event) => setChannelName(event.target.value)}
              />
              <Input
                placeholder="Description"
                value={channelDescription}
                onChange={(event) => setChannelDescription(event.target.value)}
              />
              <Select
                value=""
                onChange={(event) => {
                  if (event.target.value && !selectedChannelMembers.includes(event.target.value)) {
                    setSelectedChannelMembers((current) => [...current, event.target.value]);
                  }
                }}
              >
                <option value="">Add members</option>
                {activeMembers
                  .filter((member) => member.user_id !== currentUserId && !selectedChannelMembers.includes(member.user_id))
                  .map((member) => (
                    <option key={member.user_id} value={member.user_id}>
                      {memberLabel(member)}
                    </option>
                  ))}
              </Select>
              {selectedChannelMembers.length ? (
                <div className="flex flex-wrap gap-2">
                  {selectedChannelMembers.map((userId) => {
                    const member = activeMembers.find((item) => item.user_id === userId);
                    return (
                      <button
                        key={userId}
                        className="inline-flex items-center gap-1 rounded bg-zinc-100 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-200"
                        onClick={() => setSelectedChannelMembers((current) => current.filter((item) => item !== userId))}
                      >
                        {member ? memberLabel(member) : userId}
                        <X className="h-3 w-3" aria-hidden />
                      </button>
                    );
                  })}
                </div>
              ) : null}
              <Button className="w-full" disabled={!channelName.trim() || channelMutation.isPending} onClick={() => channelMutation.mutate()}>
                <MessageSquarePlus className="h-4 w-4" aria-hidden />
                Create channel
              </Button>
            </div>
            <div className="space-y-2 border-t border-zinc-100 pt-3">
              <Label htmlFor="new-direct">New direct message</Label>
              <div className="flex gap-2">
                <Select id="new-direct" value={directUserId} onChange={(event) => setDirectUserId(event.target.value)}>
                  <option value="">Select member</option>
                  {activeMembers
                    .filter((member) => member.user_id !== currentUserId)
                    .map((member) => (
                      <option key={member.user_id} value={member.user_id}>
                        {memberLabel(member)}
                      </option>
                    ))}
                </Select>
                <Button size="icon" disabled={!directUserId || directMutation.isPending} onClick={() => directMutation.mutate(directUserId)}>
                  <Plus className="h-4 w-4" aria-hidden />
                </Button>
              </div>
            </div>
          </div>
        </div>
      </Panel>

      <Panel className="flex min-h-0 flex-col overflow-hidden">
        <div className="border-b border-zinc-200 px-5 py-4">
          {activeConversation ? (
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {activeConversation.kind === "channel" ? (
                    <Hash className="h-5 w-5 text-zinc-500" aria-hidden />
                  ) : (
                    <AtSign className="h-5 w-5 text-zinc-500" aria-hidden />
                  )}
                  <h2 className="truncate text-xl font-semibold text-zinc-950">
                    {conversationDisplayName(activeConversation, currentUserId)}
                  </h2>
                </div>
                <p className="mt-1 text-sm text-zinc-500">
                  {activeConversation.description ||
                    `${activeConversation.participants.length} member${activeConversation.participants.length === 1 ? "" : "s"}`}
                </p>
              </div>
              <Badge tone={activeConversation.kind === "channel" ? "blue" : "green"}>
                {activeConversation.kind === "channel" ? "Channel" : "Direct"}
              </Badge>
            </div>
          ) : (
            <div>
              <h2 className="text-xl font-semibold text-zinc-950">Team chat</h2>
              <p className="mt-1 text-sm text-zinc-500">Create a channel or start a direct message.</p>
            </div>
          )}
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-auto bg-zinc-50 px-5 py-4">
          <ErrorBox message={error} />
          {!activeConversation ? (
            <div className="flex h-full items-center justify-center text-center">
              <div>
                <Users className="mx-auto h-10 w-10 text-zinc-400" aria-hidden />
                <h3 className="mt-4 font-semibold text-zinc-950">No conversation selected</h3>
                <p className="mt-2 max-w-md text-sm text-zinc-500">Pick a channel or direct message from the sidebar.</p>
              </div>
            </div>
          ) : null}
          {(messages.data ?? []).map((message) => (
            <MessageRow
              key={message.id}
              currentUserId={currentUserId}
              editingContent={editingContent}
              editingMessageId={editingMessageId}
              message={message}
              onCancelEdit={() => {
                setEditingMessageId("");
                setEditingContent("");
              }}
              onDelete={deleteMessage}
              onEdit={(item) => {
                setEditingMessageId(item.id);
                setEditingContent(item.content);
              }}
              onEditingContentChange={setEditingContent}
              onSave={saveEdit}
            />
          ))}
        </div>
        <div className="border-t border-zinc-200 p-4">
          <Textarea
            className="min-h-20"
            disabled={!activeConversation}
            placeholder={activeConversation ? `Message ${conversationDisplayName(activeConversation, currentUserId)}` : "Select a conversation"}
            value={messageText}
            onChange={(event) => setMessageText(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") sendMessage();
            }}
          />
          <div className="mt-3 flex items-center justify-between gap-3">
            <span className="text-xs text-zinc-500">
              {messages.isFetching && activeConversation ? "Syncing messages" : "Ctrl+Enter to send"}
            </span>
            <Button disabled={!activeConversation || !messageText.trim()} onClick={sendMessage}>
              <Send className="h-4 w-4" aria-hidden />
              Send
            </Button>
          </div>
        </div>
      </Panel>

      <Panel className="flex min-h-0 flex-col overflow-hidden">
        <div className="border-b border-zinc-200 p-4">
          <h3 className="font-semibold text-zinc-950">Conversation</h3>
          <p className="mt-1 text-xs text-zinc-500">
            {activeConversation?.latest_message
              ? `Last message ${formatTime(activeConversation.latest_message.created_at)}`
              : "No messages yet"}
          </p>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {activeConversation ? (
            <div className="space-y-5">
              {activeConversation.kind === "channel" ? (
                <div className="space-y-2">
                  <Label htmlFor="add-channel-member">Add member</Label>
                  <div className="flex gap-2">
                    <Select id="add-channel-member" value={addUserId} onChange={(event) => setAddUserId(event.target.value)}>
                      <option value="">Select member</option>
                      {addableMembers.map((member) => (
                        <option key={member.user_id} value={member.user_id}>
                          {memberLabel(member)}
                        </option>
                      ))}
                    </Select>
                    <Button
                      size="icon"
                      disabled={!addUserId || addParticipantMutation.isPending}
                      onClick={() => addParticipantMutation.mutate()}
                    >
                      <Plus className="h-4 w-4" aria-hidden />
                    </Button>
                  </div>
                </div>
              ) : null}
              <div>
                <p className="mb-3 text-sm font-medium text-zinc-800">Members</p>
                <div className="space-y-2">
                  {activeConversation.participants.map((participant) => (
                    <ParticipantRow key={participant.user_id} participant={participant} currentUserId={currentUserId} />
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-zinc-500">Conversation details will appear here.</p>
          )}
        </div>
      </Panel>
    </div>
      )}
    </div>
  );
}

function ConversationGroup({
  conversations,
  currentUserId,
  icon,
  label,
  selectedId,
  onSelect,
}: {
  conversations: TeamChatConversation[];
  currentUserId: string;
  icon: "channel" | "direct";
  label: string;
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const Icon = icon === "channel" ? Hash : AtSign;
  return (
    <section>
      <p className="mb-2 px-2 text-xs font-semibold uppercase text-zinc-500">{label}</p>
      <div className="space-y-1">
        {conversations.map((conversation) => {
          const selected = selectedId === conversation.id;
          return (
            <button
              key={conversation.id}
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition",
                selected ? "bg-[#f8d8ca] text-[#083d59]" : "text-zinc-700 hover:bg-zinc-100",
              )}
              onClick={() => onSelect(conversation.id)}
            >
              {conversation.kind === "direct" ? (
                <PresenceDot status={conversationPresence(conversation, currentUserId)?.chat_status ?? "offline"} />
              ) : (
                <Icon className="h-4 w-4 flex-none" aria-hidden />
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">
                  {conversationDisplayName(conversation, currentUserId)}
                </span>
                <span className="block truncate text-xs text-zinc-500">
                  {conversation.latest_message?.content ?? `${conversation.participants.length} member${conversation.participants.length === 1 ? "" : "s"}`}
                </span>
              </span>
              {conversation.unread_count ? <Badge tone="amber">{conversation.unread_count}</Badge> : null}
            </button>
          );
        })}
        {!conversations.length ? <p className="px-3 py-2 text-sm text-zinc-400">None yet</p> : null}
      </div>
    </section>
  );
}

function MessageRow({
  currentUserId,
  editingContent,
  editingMessageId,
  message,
  onCancelEdit,
  onDelete,
  onEdit,
  onEditingContentChange,
  onSave,
}: {
  currentUserId: string;
  editingContent: string;
  editingMessageId: string;
  message: TeamChatMessage;
  onCancelEdit: () => void;
  onDelete: (message: TeamChatMessage) => void;
  onEdit: (message: TeamChatMessage) => void;
  onEditingContentChange: (value: string) => void;
  onSave: (message: TeamChatMessage) => void;
}) {
  const isMine = message.user_id === currentUserId;
  const isEditing = editingMessageId === message.id;
  return (
    <div className={cn("group flex gap-3 rounded-md p-2 hover:bg-white", isMine && "bg-white/60")}>
      <div className="flex h-9 w-9 flex-none items-center justify-center rounded-md bg-[#083d59] text-sm font-semibold text-white">
        {initials(message.full_name || message.email)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="font-medium text-zinc-950">{message.full_name || message.email}</span>
          <span className="text-xs text-zinc-500">{formatTime(message.created_at)}</span>
          {message.edited_at && !message.deleted_at ? <span className="text-xs text-zinc-400">edited</span> : null}
        </div>
        {isEditing ? (
          <div className="mt-2 space-y-2">
            <Textarea
              className="min-h-20"
              value={editingContent}
              onChange={(event) => onEditingContentChange(event.target.value)}
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={() => onSave(message)}>
                <Check className="h-4 w-4" aria-hidden />
                Save
              </Button>
              <Button size="sm" variant="secondary" onClick={onCancelEdit}>
                <X className="h-4 w-4" aria-hidden />
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <p className={cn("mt-1 whitespace-pre-wrap text-sm leading-6", message.deleted_at ? "italic text-zinc-400" : "text-zinc-800")}>
            {message.content}
          </p>
        )}
      </div>
      {isMine && !message.deleted_at && !isEditing ? (
        <div className="flex flex-none gap-1 opacity-0 transition group-hover:opacity-100">
          <Button aria-label="Edit message" size="icon" variant="ghost" onClick={() => onEdit(message)}>
            <Pencil className="h-4 w-4" aria-hidden />
          </Button>
          <Button aria-label="Delete message" size="icon" variant="ghost" onClick={() => onDelete(message)}>
            <Trash2 className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function ParticipantRow({ participant, currentUserId }: { participant: TeamChatParticipant; currentUserId: string }) {
  const presence = presenceMeta(participant.chat_status);
  return (
    <div className="flex items-center gap-3 rounded-md bg-zinc-50 p-2">
      <div className="relative flex-none">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-white text-xs font-semibold text-[#083d59] shadow-sm">
          {initials(participant.full_name || participant.email)}
        </div>
        <span className={cn("absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-zinc-50", presence.dot)} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-zinc-900">
          {participant.full_name || participant.email}
          {participant.user_id === currentUserId ? " (you)" : ""}
        </p>
        <p className="truncate text-xs text-zinc-500">
          {presence.label}
          {participant.status_message ? ` - ${participant.status_message}` : ` - ${participant.email}`}
        </p>
      </div>
      <Badge tone={participant.role === "owner" ? "blue" : "neutral"}>{participant.role}</Badge>
    </div>
  );
}

function conversationDisplayName(conversation: TeamChatConversation, currentUserId: string) {
  if (conversation.kind === "channel") return conversation.name ? `# ${conversation.name}` : "# channel";
  const other = conversationPresence(conversation, currentUserId);
  return other?.full_name || other?.email || "Direct message";
}

function conversationPresence(conversation: TeamChatConversation, currentUserId: string) {
  return conversation.participants.find((participant) => participant.user_id !== currentUserId);
}

function memberLabel(member: MemberOption) {
  return member.full_name ? `${member.full_name} (${member.email})` : member.email;
}

function initials(value: string) {
  const parts = value.split(/[ @._-]+/).filter(Boolean);
  return (parts[0]?.[0] ?? "?").concat(parts[1]?.[0] ?? "").toUpperCase();
}

function PresenceDot({ status }: { status: ChatPresenceStatus }) {
  return <span className={cn("h-2.5 w-2.5 flex-none rounded-full", presenceMeta(status).dot)} aria-hidden />;
}

function presenceMeta(status: ChatPresenceStatus) {
  if (status === "online") return { label: "Online", dot: "bg-emerald-500" };
  if (status === "busy") return { label: "Busy", dot: "bg-rose-500" };
  if (status === "away") return { label: "Away", dot: "bg-amber-500" };
  if (status === "do_not_disturb") return { label: "Do not disturb", dot: "bg-red-700" };
  return { label: "Unavailable", dot: "bg-zinc-400" };
}

function formatTime(value?: string | null) {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}
