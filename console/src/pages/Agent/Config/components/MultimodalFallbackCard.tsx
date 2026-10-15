import { useEffect, useState } from "react";
import { Card, Form, Select, Switch } from "@agentscope-ai/design";
import { ScanEye } from "lucide-react";
import { useTranslation } from "react-i18next";
import api from "@/api";
import type { ProviderInfo } from "@/api/types/provider";
import { NumberStepper } from "@/components/interaction/NumberStepper";
import { SettingsField } from "@/components/interaction/SettingsField";
import { useAgentStore } from "@/stores/agentStore";
import styles from "../index.module.less";

function visionModels(provider?: ProviderInfo) {
  return [
    ...(provider?.models ?? []),
    ...(provider?.extra_models ?? []),
  ].filter((model) => model.supports_image === true);
}

export function MultimodalFallbackCard() {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const { selectedAgent } = useAgentStore();
  const enabled = Form.useWatch(["multimodal_fallback", "enabled"], form);
  const providerId = Form.useWatch(
    ["multimodal_fallback", "vision_provider"],
    form,
  );
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let current = true;
    setLoading(true);
    setFailed(false);
    const load = async () => {
      try {
        const result = await api.listProviders();
        if (current) setProviders(result);
      } catch {
        if (current) setFailed(true);
      } finally {
        if (current) setLoading(false);
      }
    };
    void load();
    return () => {
      current = false;
    };
  }, [selectedAgent]);
  const available = providers.filter(
    (provider) => provider.enabled !== false && visionModels(provider).length,
  );
  const models = visionModels(available.find((item) => item.id === providerId));
  const required = {
    required: !!enabled,
    message: t("visionFallback.required"),
  };

  return (
    <Card
      className={styles.formCard}
      title={
        <span>
          <ScanEye size={16} aria-hidden="true" /> {t("visionFallback.title")}
        </span>
      }
    >
      <p>{t("visionFallback.description")}</p>
      {failed && <p role="alert">{t("visionFallback.loadFailed")}</p>}
      <SettingsField
        name={["multimodal_fallback", "enabled"]}
        label={t("visionFallback.enabled")}
        valuePropName="checked"
      >
        <Switch />
      </SettingsField>
      <SettingsField
        name={["multimodal_fallback", "vision_provider"]}
        label={t("visionFallback.provider")}
        rules={[required]}
      >
        <Select
          loading={loading}
          disabled={!enabled}
          options={available.map((provider) => ({
            value: provider.id,
            label: provider.name,
          }))}
          onChange={() =>
            form.setFieldValue(["multimodal_fallback", "vision_model"], "")
          }
        />
      </SettingsField>
      <SettingsField
        name={["multimodal_fallback", "vision_model"]}
        label={t("visionFallback.model")}
        rules={[required]}
      >
        <Select
          disabled={!enabled || !providerId}
          options={models.map((model) => ({
            value: model.id,
            label: model.name,
          }))}
        />
      </SettingsField>
      <div className={styles.llmRetryRow}>
        {(
          [
            ["max_images_per_turn", "images", 1, 50],
            ["description_max_tokens", "tokens", 64, 4096],
            ["timeout_seconds", "timeout", 1, 300],
          ] as const
        ).map(([field, label, min, max]) => (
          <SettingsField
            key={field}
            name={["multimodal_fallback", field]}
            label={t(`visionFallback.${label}`)}
            className={styles.llmRetryField}
            rules={[{ ...required, type: "number", min, max }]}
          >
            <NumberStepper min={min} max={max} step={1} disabled={!enabled} />
          </SettingsField>
        ))}
      </div>
    </Card>
  );
}
