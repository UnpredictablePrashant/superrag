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
  updateTeamChatMessage,
  updateTeamChatPresence,
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
  ChevronDown,
  Hash,
  MessageCircle,
  MessageSquare,
  MessageSquarePlus,
  Pencil,
  Plus,
  Search,
  Send,
  Trash2,
  UserPlus,
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
  const [channelMemberSearch, setChannelMemberSearch] = React.useState("");
  const [conversationSearch, setConversationSearch] = React.useState("");
  const [peopleSearch, setPeopleSearch] = React.useState("");
  const [editingMessageId, setEditingMessageId] = React.useState("");
  const [editingContent, setEditingContent] = React.useState("");
  const [presenceStatus, setPresenceStatus] = React.useState<ChatPresenceStatus>("online");
  const [presenceMessage, setPresenceMessage] = React.useState("");
  const [statusMenuOpen, setStatusMenuOpen] = React.useState(false);
  const [createMenuOpen, setCreateMenuOpen] = React.useState(false);
  const [createDialog, setCreateDialog] = React.useState<"channel" | "direct" | null>(null);
  const [addMembersConversationId, setAddMembersConversationId] = React.useState("");
  const [selectedAddMembers, setSelectedAddMembers] = React.useState<string[]>([]);
  const [addMemberSearch, setAddMemberSearch] = React.useState("");
  const [error, setError] = React.useState("");

  const me = useQuery({ queryKey: ["me"], queryFn: getMe });
  const members = useQuery({ queryKey: ["members"], queryFn: listMembers });
  const conversations = useQuery({
    queryKey: ["team-chat-conversations"],
    queryFn: listTeamChatConversations,
    refetchInterval: 5000,
  });
  const activeConversation = conversations.data?.find((conversation) => conversation.id === activeConversationId);
  const addMembersConversation = conversations.data?.find((conversation) => conversation.id === addMembersConversationId);
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
  const currentUserId = me.data?.user?.id ?? "";
  const currentMember = activeMembers.find((member) => member.user_id === currentUserId);

  React.useEffect(() => {
    if (!currentMember) return;
    setPresenceStatus(currentMember.chat_status);
    setPresenceMessage(currentMember.status_message ?? "");
  }, [currentMember]);

  const presenceMutation = useMutation({
    mutationFn: () => updateTeamChatPresence(presenceStatus, presenceMessage),
    onSuccess: () => {
      setError("");
      setStatusMenuOpen(false);
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
      setChannelMemberSearch("");
      setCreateDialog(null);
      setError("");
      queryClient.invalidateQueries({ queryKey: ["team-chat-conversations"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not create channel."),
  });

  const directMutation = useMutation({
    mutationFn: createTeamChatDirect,
    onSuccess: (conversation) => {
      setActiveConversationId(conversation.id);
      setPeopleSearch("");
      setCreateDialog(null);
      setError("");
      queryClient.invalidateQueries({ queryKey: ["team-chat-conversations"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not start direct message."),
  });

  const addParticipantMutation = useMutation({
    mutationFn: ({ conversationId, userIds }: { conversationId: string; userIds: string[] }) =>
      addTeamChatParticipants(conversationId, userIds),
    onSuccess: (conversation) => {
      setActiveConversationId(conversation.id);
      setAddMembersConversationId("");
      setSelectedAddMembers([]);
      setAddMemberSearch("");
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

  function openAddMembers(conversationId: string) {
    setAddMembersConversationId(conversationId);
    setSelectedAddMembers([]);
    setAddMemberSearch("");
  }

  const filteredConversations = (conversations.data ?? []).filter((conversation) => {
    const search = conversationSearch.toLowerCase();
    const title = conversationDisplayName(conversation, currentUserId).toLowerCase();
    const latest = conversation.latest_message?.content.toLowerCase() ?? "";
    return title.includes(search) || latest.includes(search);
  });
  const recentConversations = [...filteredConversations].sort((a, b) =>
    (b.last_message_at ?? b.updated_at).localeCompare(a.last_message_at ?? a.updated_at),
  );
  const channels = filteredConversations.filter((conversation) => conversation.kind === "channel");
  const directs = filteredConversations.filter((conversation) => conversation.kind === "direct");
  const visiblePeople = activeMembers.filter((member) => {
    const search = peopleSearch.toLowerCase();
    return member.user_id !== currentUserId && memberLabel(member).toLowerCase().includes(search);
  });
  const channelMemberOptions = activeMembers.filter(
    (member) =>
      member.user_id !== currentUserId &&
      !selectedChannelMembers.includes(member.user_id) &&
      memberLabel(member).toLowerCase().includes(channelMemberSearch.toLowerCase()),
  );
  const addableMembers = activeMembers.filter(
    (member) =>
      member.user_id !== currentUserId &&
      !addMembersConversation?.participants.some((participant) => participant.user_id === member.user_id) &&
      !selectedAddMembers.includes(member.user_id) &&
      memberLabel(member).toLowerCase().includes(addMemberSearch.toLowerCase()),
  );
  const onlineCount = activeMembers.filter((member) => member.chat_status === "online").length;
  const currentPresence = presenceMeta(presenceStatus);

  return (
    <div className="h-[calc(100vh-112px)] min-h-[640px] overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-[#083d59]" aria-hidden />
              <h2 className="truncate text-base font-semibold text-zinc-950">
                {chatMode === "people" ? "Team chat" : "AI assistant"}
              </h2>
            </div>
            <p className="mt-0.5 truncate text-xs text-zinc-500">
              {chatMode === "people"
                ? `${onlineCount} available now, ${conversations.data?.length ?? 0} conversations`
                : "Ask across connected company knowledge"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {chatMode === "people" ? (
              <>
                <div className="relative">
                  <Button
                    className="h-9 px-3"
                    variant="secondary"
                    onClick={() => setStatusMenuOpen((open) => !open)}
                  >
                    <span className={cn("h-2.5 w-2.5 rounded-full", currentPresence.dot)} aria-hidden />
                    {currentPresence.label}
                    <ChevronDown className="h-4 w-4" aria-hidden />
                  </Button>
                  {statusMenuOpen ? (
                    <StatusMenu
                      isPending={presenceMutation.isPending}
                      message={presenceMessage}
                      status={presenceStatus}
                      onClose={() => setStatusMenuOpen(false)}
                      onMessageChange={setPresenceMessage}
                      onSave={() => presenceMutation.mutate()}
                      onStatusChange={setPresenceStatus}
                    />
                  ) : null}
                </div>
                <div className="relative">
                  <Button
                    aria-label="Create chat or channel"
                    size="icon"
                    title="Create"
                    onClick={() => setCreateMenuOpen((open) => !open)}
                  >
                    <Plus className="h-4 w-4" aria-hidden />
                  </Button>
                  {createMenuOpen ? (
                    <CreateMenu
                      onSelect={(mode) => {
                        setCreateDialog(mode);
                        setCreateMenuOpen(false);
                      }}
                    />
                  ) : null}
                </div>
              </>
            ) : null}
            <Button
              className="h-9 px-3"
              variant={chatMode === "ai" ? "primary" : "secondary"}
              onClick={() => setChatMode(chatMode === "ai" ? "people" : "ai")}
            >
              {chatMode === "ai" ? <MessageSquare className="h-4 w-4" aria-hidden /> : <Bot className="h-4 w-4" aria-hidden />}
              {chatMode === "ai" ? "People" : "AI assistant"}
            </Button>
          </div>
        </div>

        {chatMode === "ai" ? (
          <div className="min-h-0 flex-1 p-4">
            <AskWorkspace compact />
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)] xl:grid-cols-[300px_minmax(0,1fr)_280px]">
            <Panel className="flex min-h-0 flex-col overflow-hidden rounded-none border-0 border-r border-zinc-200 shadow-none">
              <div className="border-b border-zinc-200 p-3">
                <SearchInput
                  placeholder="Search chats"
                  value={conversationSearch}
                  onChange={setConversationSearch}
                />
              </div>
              <div className="min-h-0 flex-1 space-y-4 overflow-auto p-3">
                <ConversationGroup
                  conversations={recentConversations.slice(0, 5)}
                  currentUserId={currentUserId}
                  label="Recent"
                  selectedId={activeConversationId}
                  onAddMembers={openAddMembers}
                  onSelect={setActiveConversationId}
                />
                <ConversationGroup
                  conversations={channels}
                  currentUserId={currentUserId}
                  label="Channels"
                  selectedId={activeConversationId}
                  onAddMembers={openAddMembers}
                  onSelect={setActiveConversationId}
                />
                <ConversationGroup
                  conversations={directs}
                  currentUserId={currentUserId}
                  label="Direct messages"
                  selectedId={activeConversationId}
                  onAddMembers={openAddMembers}
                  onSelect={setActiveConversationId}
                />
              </div>
            </Panel>

            <Panel className="flex min-h-0 flex-col overflow-hidden rounded-none border-0 shadow-none">
              <div className="border-b border-zinc-200 px-4 py-3">
                {activeConversation ? (
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        {activeConversation.kind === "channel" ? (
                          <Hash className="h-4 w-4 text-zinc-500" aria-hidden />
                        ) : (
                          <AtSign className="h-4 w-4 text-zinc-500" aria-hidden />
                        )}
                        <h2 className="truncate text-base font-semibold text-zinc-950">
                          {conversationDisplayName(activeConversation, currentUserId)}
                        </h2>
                      </div>
                      <p className="mt-0.5 truncate text-xs text-zinc-500">
                        {activeConversation.description ||
                          `${activeConversation.participants.length} member${activeConversation.participants.length === 1 ? "" : "s"}`}
                      </p>
                    </div>
                    {activeConversation.kind === "channel" ? (
                      <Button
                        aria-label="Add people"
                        size="icon"
                        title="Add people"
                        variant="secondary"
                        onClick={() => openAddMembers(activeConversation.id)}
                      >
                        <UserPlus className="h-4 w-4" aria-hidden />
                      </Button>
                    ) : null}
                  </div>
                ) : (
                  <div>
                    <h2 className="text-base font-semibold text-zinc-950">Pick a conversation</h2>
                    <p className="mt-0.5 text-xs text-zinc-500">Recent chats and available people are visible around the thread.</p>
                  </div>
                )}
              </div>
              <div className="min-h-0 flex-1 space-y-2 overflow-auto bg-zinc-50 px-4 py-3">
                <ErrorBox message={error} />
                {!activeConversation ? (
                  <div className="flex h-full items-center justify-center text-center">
                    <div>
                      <Users className="mx-auto h-9 w-9 text-zinc-400" aria-hidden />
                      <h3 className="mt-3 font-semibold text-zinc-950">No conversation selected</h3>
                      <p className="mt-1 max-w-md text-sm text-zinc-500">Select a recent chat or start one from the plus menu.</p>
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
              <div className="border-t border-zinc-200 p-3">
                <div className="flex items-end gap-2">
                  <Textarea
                    className="min-h-12 resize-none"
                    disabled={!activeConversation}
                    placeholder={
                      activeConversation
                        ? `Message ${conversationDisplayName(activeConversation, currentUserId)}`
                        : "Select a conversation"
                    }
                    rows={2}
                    value={messageText}
                    onChange={(event) => setMessageText(event.target.value)}
                    onKeyDown={(event) => {
                      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") sendMessage();
                    }}
                  />
                  <Button
                    aria-label="Send message"
                    className="h-10 w-10 flex-none px-0"
                    disabled={!activeConversation || !messageText.trim()}
                    onClick={sendMessage}
                  >
                    <Send className="h-4 w-4" aria-hidden />
                  </Button>
                </div>
                <p className="mt-2 text-xs text-zinc-500">
                  {messages.isFetching && activeConversation ? "Syncing messages" : "Ctrl+Enter to send"}
                </p>
              </div>
            </Panel>

            <Panel className="hidden min-h-0 flex-col overflow-hidden rounded-none border-0 border-l border-zinc-200 shadow-none xl:flex">
              <div className="border-b border-zinc-200 p-3">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-zinc-950">People</h3>
                  <Badge tone="green">{onlineCount} online</Badge>
                </div>
                <SearchInput placeholder="Search users" value={peopleSearch} onChange={setPeopleSearch} />
              </div>
              <div className="min-h-0 flex-1 overflow-auto p-2">
                {visiblePeople.map((member) => (
                  <PeopleRow
                    key={member.user_id}
                    member={member}
                    onMessage={(userId) => directMutation.mutate(userId)}
                  />
                ))}
                {!visiblePeople.length ? <p className="px-2 py-3 text-sm text-zinc-400">No users found</p> : null}
              </div>
            </Panel>
          </div>
        )}
      </div>

      {createDialog ? (
        <CreateConversationDialog
          channelDescription={channelDescription}
          channelMemberOptions={channelMemberOptions}
          channelMemberSearch={channelMemberSearch}
          channelName={channelName}
          isCreatingChannel={channelMutation.isPending}
          isCreatingDirect={directMutation.isPending}
          mode={createDialog}
          people={visiblePeople}
          selectedChannelMembers={selectedChannelMembers}
          onChannelDescriptionChange={setChannelDescription}
          onChannelMemberSearchChange={setChannelMemberSearch}
          onChannelNameChange={setChannelName}
          onClose={() => setCreateDialog(null)}
          onCreateChannel={() => channelMutation.mutate()}
          onRemoveChannelMember={(userId) =>
            setSelectedChannelMembers((current) => current.filter((item) => item !== userId))
          }
          onSelectChannelMember={(userId) => setSelectedChannelMembers((current) => [...current, userId])}
          onStartDirect={(userId) => directMutation.mutate(userId)}
          selectedMembers={activeMembers.filter((member) => selectedChannelMembers.includes(member.user_id))}
        />
      ) : null}

      {addMembersConversation ? (
        <AddMembersDialog
          addableMembers={addableMembers}
          conversation={addMembersConversation}
          isPending={addParticipantMutation.isPending}
          search={addMemberSearch}
          selectedMembers={activeMembers.filter((member) => selectedAddMembers.includes(member.user_id))}
          onAdd={() =>
            addParticipantMutation.mutate({
              conversationId: addMembersConversation.id,
              userIds: selectedAddMembers,
            })
          }
          onClose={() => setAddMembersConversationId("")}
          onRemove={(userId) => setSelectedAddMembers((current) => current.filter((item) => item !== userId))}
          onSearchChange={setAddMemberSearch}
          onSelect={(userId) => setSelectedAddMembers((current) => [...current, userId])}
        />
      ) : null}
    </div>
  );
}

function StatusMenu({
  isPending,
  message,
  status,
  onClose,
  onMessageChange,
  onSave,
  onStatusChange,
}: {
  isPending: boolean;
  message: string;
  status: ChatPresenceStatus;
  onClose: () => void;
  onMessageChange: (value: string) => void;
  onSave: () => void;
  onStatusChange: (value: ChatPresenceStatus) => void;
}) {
  return (
    <div className="absolute right-0 top-11 z-30 w-72 rounded-md border border-zinc-200 bg-white p-3 shadow-lg">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold text-zinc-950">My status</p>
        <Button aria-label="Close status menu" size="icon" variant="ghost" onClick={onClose}>
          <X className="h-4 w-4" aria-hidden />
        </Button>
      </div>
      <div className="space-y-2">
        <Select value={status} onChange={(event) => onStatusChange(event.target.value as ChatPresenceStatus)}>
          {presenceOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <Input
          maxLength={160}
          placeholder="Status message"
          value={message}
          onChange={(event) => onMessageChange(event.target.value)}
        />
        <Button className="w-full" disabled={isPending} size="sm" onClick={onSave}>
          Save status
        </Button>
      </div>
    </div>
  );
}

function CreateMenu({ onSelect }: { onSelect: (mode: "channel" | "direct") => void }) {
  return (
    <div className="absolute right-0 top-11 z-30 w-56 overflow-hidden rounded-md border border-zinc-200 bg-white p-1 shadow-lg">
      <button
        className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-100"
        onClick={() => onSelect("channel")}
      >
        <Hash className="h-4 w-4" aria-hidden />
        Create channel
      </button>
      <button
        className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-100"
        onClick={() => onSelect("direct")}
      >
        <MessageCircle className="h-4 w-4" aria-hidden />
        New direct message
      </button>
    </div>
  );
}

function CreateConversationDialog({
  channelDescription,
  channelMemberOptions,
  channelMemberSearch,
  channelName,
  isCreatingChannel,
  isCreatingDirect,
  mode,
  people,
  selectedChannelMembers,
  selectedMembers,
  onChannelDescriptionChange,
  onChannelMemberSearchChange,
  onChannelNameChange,
  onClose,
  onCreateChannel,
  onRemoveChannelMember,
  onSelectChannelMember,
  onStartDirect,
}: {
  channelDescription: string;
  channelMemberOptions: MemberOption[];
  channelMemberSearch: string;
  channelName: string;
  isCreatingChannel: boolean;
  isCreatingDirect: boolean;
  mode: "channel" | "direct";
  people: MemberOption[];
  selectedChannelMembers: string[];
  selectedMembers: MemberOption[];
  onChannelDescriptionChange: (value: string) => void;
  onChannelMemberSearchChange: (value: string) => void;
  onChannelNameChange: (value: string) => void;
  onClose: () => void;
  onCreateChannel: () => void;
  onRemoveChannelMember: (userId: string) => void;
  onSelectChannelMember: (userId: string) => void;
  onStartDirect: (userId: string) => void;
}) {
  return (
    <Dialog onClose={onClose} title={mode === "channel" ? "Create channel" : "Start direct message"}>
      {mode === "channel" ? (
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="new-channel">Channel name</Label>
            <Input
              id="new-channel"
              placeholder="project-updates"
              value={channelName}
              onChange={(event) => onChannelNameChange(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="channel-description">Description</Label>
            <Input
              id="channel-description"
              placeholder="Optional"
              value={channelDescription}
              onChange={(event) => onChannelDescriptionChange(event.target.value)}
            />
          </div>
          <MemberPicker
            emptyLabel="Type a few letters to find people"
            members={channelMemberOptions}
            search={channelMemberSearch}
            selectedMembers={selectedMembers}
            onRemove={onRemoveChannelMember}
            onSearchChange={onChannelMemberSearchChange}
            onSelect={onSelectChannelMember}
          />
          <Button
            className="w-full"
            disabled={!channelName.trim() || isCreatingChannel}
            onClick={onCreateChannel}
          >
            <MessageSquarePlus className="h-4 w-4" aria-hidden />
            Create channel
          </Button>
          {selectedChannelMembers.length ? null : (
            <p className="text-xs text-zinc-500">You can add people now or use the plus icon on the channel later.</p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {people.map((member) => (
            <PeopleRow
              key={member.user_id}
              member={member}
              onMessage={(userId) => onStartDirect(userId)}
              pending={isCreatingDirect}
            />
          ))}
          {!people.length ? <p className="py-4 text-sm text-zinc-500">Search users from the people panel first.</p> : null}
        </div>
      )}
    </Dialog>
  );
}

function AddMembersDialog({
  addableMembers,
  conversation,
  isPending,
  search,
  selectedMembers,
  onAdd,
  onClose,
  onRemove,
  onSearchChange,
  onSelect,
}: {
  addableMembers: MemberOption[];
  conversation: TeamChatConversation;
  isPending: boolean;
  search: string;
  selectedMembers: MemberOption[];
  onAdd: () => void;
  onClose: () => void;
  onRemove: (userId: string) => void;
  onSearchChange: (value: string) => void;
  onSelect: (userId: string) => void;
}) {
  return (
    <Dialog onClose={onClose} title={`Add people to ${conversation.name ?? "channel"}`}>
      <div className="space-y-4">
        <MemberPicker
          emptyLabel="No matching people to add"
          members={addableMembers}
          search={search}
          selectedMembers={selectedMembers}
          onRemove={onRemove}
          onSearchChange={onSearchChange}
          onSelect={onSelect}
        />
        <Button className="w-full" disabled={!selectedMembers.length || isPending} onClick={onAdd}>
          <UserPlus className="h-4 w-4" aria-hidden />
          Add selected people
        </Button>
      </div>
    </Dialog>
  );
}

function MemberPicker({
  emptyLabel,
  members,
  search,
  selectedMembers,
  onRemove,
  onSearchChange,
  onSelect,
}: {
  emptyLabel: string;
  members: MemberOption[];
  search: string;
  selectedMembers: MemberOption[];
  onRemove: (userId: string) => void;
  onSearchChange: (value: string) => void;
  onSelect: (userId: string) => void;
}) {
  return (
    <div className="space-y-3">
      <SearchInput placeholder="Search people" value={search} onChange={onSearchChange} />
      {selectedMembers.length ? (
        <div className="flex flex-wrap gap-2">
          {selectedMembers.map((member) => (
            <button
              key={member.user_id}
              className="inline-flex items-center gap-1 rounded bg-zinc-100 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-200"
              onClick={() => onRemove(member.user_id)}
            >
              {member.full_name || member.email}
              <X className="h-3 w-3" aria-hidden />
            </button>
          ))}
        </div>
      ) : null}
      <div className="max-h-64 space-y-1 overflow-auto rounded-md border border-zinc-200 p-1">
        {members.map((member) => (
          <button
            key={member.user_id}
            className="flex w-full items-center gap-3 rounded px-2 py-2 text-left hover:bg-zinc-100"
            onClick={() => onSelect(member.user_id)}
          >
            <MemberAvatar label={member.full_name || member.email} status={member.chat_status} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-zinc-900">{member.full_name || member.email}</span>
              <span className="block truncate text-xs text-zinc-500">{member.email}</span>
            </span>
            <Plus className="h-4 w-4 text-zinc-500" aria-hidden />
          </button>
        ))}
        {!members.length ? <p className="px-2 py-4 text-center text-sm text-zinc-400">{emptyLabel}</p> : null}
      </div>
    </div>
  );
}

function Dialog({ children, onClose, title }: { children: React.ReactNode; onClose: () => void; title: string }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-zinc-950/30 p-4">
      <div className="w-full max-w-lg rounded-lg border border-zinc-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3">
          <h3 className="font-semibold text-zinc-950">{title}</h3>
          <Button aria-label="Close dialog" size="icon" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" aria-hidden />
          </Button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

function SearchInput({
  placeholder,
  value,
  onChange,
}: {
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-zinc-400" aria-hidden />
      <Input
        className="pl-9"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function ConversationGroup({
  conversations,
  currentUserId,
  label,
  selectedId,
  onAddMembers,
  onSelect,
}: {
  conversations: TeamChatConversation[];
  currentUserId: string;
  label: string;
  selectedId: string;
  onAddMembers: (conversationId: string) => void;
  onSelect: (id: string) => void;
}) {
  return (
    <section>
      <p className="mb-2 px-2 text-xs font-semibold uppercase text-zinc-500">{label}</p>
      <div className="space-y-1">
        {conversations.map((conversation) => {
          const selected = selectedId === conversation.id;
          const title = conversationDisplayName(conversation, currentUserId);
          return (
            <div
              key={`${label}-${conversation.id}`}
              className={cn(
                "group flex items-center gap-1 rounded-md transition",
                selected ? "bg-[#f8d8ca] text-[#083d59]" : "text-zinc-700 hover:bg-zinc-100",
              )}
            >
              <button className="flex min-w-0 flex-1 items-center gap-3 px-3 py-2 text-left" onClick={() => onSelect(conversation.id)}>
                {conversation.kind === "direct" ? (
                  <PresenceDot status={conversationPresence(conversation, currentUserId)?.chat_status ?? "offline"} />
                ) : (
                  <Hash className="h-4 w-4 flex-none" aria-hidden />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{title}</span>
                  <span className="block truncate text-xs text-zinc-500">
                    {conversation.latest_message?.content ??
                      `${conversation.participants.length} member${conversation.participants.length === 1 ? "" : "s"}`}
                  </span>
                </span>
                {conversation.unread_count ? <Badge tone="amber">{conversation.unread_count}</Badge> : null}
              </button>
              {conversation.kind === "channel" ? (
                <Button
                  aria-label={`Add people to ${title}`}
                  className="mr-1 opacity-0 group-hover:opacity-100 focus:opacity-100"
                  size="icon"
                  title="Add people"
                  variant="ghost"
                  onClick={() => onAddMembers(conversation.id)}
                >
                  <Plus className="h-4 w-4" aria-hidden />
                </Button>
              ) : null}
            </div>
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
    <div className={cn("group flex gap-3 rounded-md p-2 hover:bg-white", isMine && "bg-white/70")}>
      <div className="flex h-8 w-8 flex-none items-center justify-center rounded-md bg-[#083d59] text-xs font-semibold text-white">
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

function PeopleRow({
  member,
  onMessage,
  pending = false,
}: {
  member: MemberOption;
  onMessage: (userId: string) => void;
  pending?: boolean;
}) {
  const presence = presenceMeta(member.chat_status);
  return (
    <div className="flex items-center gap-3 rounded-md px-2 py-2 hover:bg-zinc-50">
      <MemberAvatar label={member.full_name || member.email} status={member.chat_status} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-zinc-900">{member.full_name || member.email}</p>
        <p className="truncate text-xs text-zinc-500">
          {presence.label}
          {member.status_message ? ` - ${member.status_message}` : ""}
        </p>
      </div>
      <Button
        aria-label={`Message ${member.full_name || member.email}`}
        disabled={pending}
        size="icon"
        title="Message"
        variant="ghost"
        onClick={() => onMessage(member.user_id)}
      >
        <MessageSquare className="h-4 w-4" aria-hidden />
      </Button>
    </div>
  );
}

function MemberAvatar({ label, status }: { label: string; status: ChatPresenceStatus }) {
  return (
    <div className="relative flex-none">
      <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[#083d59] text-xs font-semibold text-white">
        {initials(label)}
      </div>
      <span className={cn("absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white", presenceMeta(status).dot)} />
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

function memberLabel(member: MemberOption | TeamChatParticipant) {
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
