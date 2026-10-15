import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Form } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ProviderInfo } from "@/api/types/provider";
import { MultimodalFallbackCard } from "./MultimodalFallbackCard";

const mocks = vi.hoisted(() => ({ listProviders: vi.fn() }));
vi.mock("@/api", () => ({ default: mocks }));
vi.mock("@agentscope-ai/design", async () => await import("antd"));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@/stores/agentStore", () => ({
  useAgentStore: () => ({ selectedAgent: "default" }),
}));

const provider = {
  id: "local",
  name: "Local Vision",
  enabled: true,
  models: [
    { id: "vision", name: "Vision", supports_image: true },
    {
      id: "audio",
      name: "Audio",
      supports_image: false,
      supports_multimodal: true,
    },
  ],
  extra_models: [],
} as unknown as ProviderInfo;

function Harness() {
  return (
    <Form
      initialValues={{
        multimodal_fallback: {
          enabled: true,
          vision_provider: "local",
          vision_model: "vision",
          max_images_per_turn: 5,
          description_max_tokens: 1024,
          timeout_seconds: 60,
        },
      }}
    >
      <MultimodalFallbackCard />
    </Form>
  );
}

describe("image description settings", () => {
  beforeEach(() => {
    mocks.listProviders.mockReset();
  });
  it("only offers models with explicit image support", async () => {
    mocks.listProviders.mockResolvedValue([provider]);
    render(<Harness />);
    await screen.findByText("Local Vision");
    expect(screen.getByText("Vision")).toBeVisible();
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "visionFallback.model" }));
    await screen.findByRole("option", { name: "Vision" });
    expect(screen.queryByRole("option", { name: "Audio" })).toBeNull();
    fireEvent.click(screen.getByRole("switch"));
    await waitFor(() =>
      expect(screen.getByRole("switch")).toHaveAttribute(
        "aria-checked",
        "false",
      ),
    );
  });
  it("reports provider discovery failure", async () => {
    mocks.listProviders.mockRejectedValue(new Error("offline"));
    render(<Harness />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "visionFallback.loadFailed",
    );
  });
});
