import { useEffect, useMemo, useState } from "react";
import Select, { type SingleValue } from "react-select";

import { ModalCloseButton } from "./ModalCloseButton";
import { Button } from "./ui";
import { parseApiError } from "../lib/format";
import type { ReportConfig, ReportConfigLine, ReportGroupSelection } from "../types";

type Props = {
  config: ReportConfig | null;
  kind: "dre" | "dro";
  loading: boolean;
  saving: boolean;
  onClose: () => void;
  onSave: (payload: { lines: ReportConfigLine[] }) => Promise<ReportConfig>;
};

type SelectOption = {
  value: string;
  label: string;
};

function newLineId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `line-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function makeEmptyLine(): ReportConfigLine {
  return {
    id: newLineId(),
    name: "Nova linha",
    order: 0,
    line_type: "source",
    operation: "add",
    special_source: null,
    category_groups: [],
    formula: [],
    show_on_dashboard: false,
    show_percent: true,
    percent_mode: "grouped_children",
    percent_reference_line_id: null,
    is_active: true,
    is_hidden: false,
    summary_binding: null,
  };
}

function moveItem<T>(items: T[], fromIndex: number, toIndex: number) {
  const next = [...items];
  const [item] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, item);
  return next;
}

function normalizeOrders(lines: ReportConfigLine[]) {
  return lines.map((line, index) => ({ ...line, order: index + 1 }));
}

function asSingleValue(option: SingleValue<SelectOption>) {
  return option?.value ?? "";
}

function makeEmptyGroupSelection(defaultOperation: ReportConfigLine["operation"] = "add"): ReportGroupSelection {
  return {
    group_name: "",
    operation: defaultOperation,
  };
}

export function ReportConfigModal({ config, kind, loading, saving, onClose, onSave }: Props) {
  const [draft, setDraft] = useState<ReportConfig | null>(config);
  const [error, setError] = useState("");
  const [draggedLineId, setDraggedLineId] = useState<string | null>(null);

  useEffect(() => {
    setDraft(
      config
        ? {
            ...config,
            lines: config.lines.map((line) => ({
              ...line,
              category_groups: line.category_groups.map((group) => ({ ...group })),
              formula: [...line.formula],
            })),
          }
        : null,
    );
    setError("");
  }, [config]);

  const lineOptions = useMemo<SelectOption[]>(
    () =>
      (draft?.lines ?? []).map((line, index) => ({
        value: line.id,
        label: `${index + 1}. ${line.name || "Linha sem nome"}`,
      })),
    [draft],
  );

  const groupOptions = useMemo<SelectOption[]>(
    () =>
      (draft?.available_groups ?? []).map((group) => ({
        value: group.value,
        label: `${group.scope === "group" ? "Grupo" : "Subgrupo"}: ${group.name} (${group.entry_kind})`,
      })),
    [draft],
  );

  const specialSourceOptions = useMemo<SelectOption[]>(
    () => (draft?.special_source_options ?? []).map((option) => ({ value: option.value, label: option.label })),
    [draft],
  );

  const unmappedGroups = useMemo(() => Array.from(new Set(draft?.unmapped_groups ?? [])), [draft]);

  if (!config || !draft) {
    return null;
  }

  function setLines(updater: (lines: ReportConfigLine[]) => ReportConfigLine[]) {
    setDraft((current) => (current ? { ...current, lines: normalizeOrders(updater(current.lines)) } : current));
  }

  function updateLine(lineId: string, updater: (line: ReportConfigLine) => ReportConfigLine) {
    setLines((lines) => lines.map((line) => (line.id === lineId ? updater(line) : line)));
  }

  function addGroupSelection(lineId: string) {
    updateLine(lineId, (current) => ({
      ...current,
      category_groups: [...current.category_groups, makeEmptyGroupSelection(current.operation)],
    }));
  }

  function updateGroupSelection(
    lineId: string,
    groupIndex: number,
    updater: (group: ReportGroupSelection) => ReportGroupSelection,
  ) {
    updateLine(lineId, (current) => ({
      ...current,
      category_groups: current.category_groups.map((group, currentIndex) =>
        currentIndex === groupIndex ? updater(group) : group,
      ),
    }));
  }

  function removeGroupSelection(lineId: string, groupIndex: number) {
    updateLine(lineId, (current) => ({
      ...current,
      category_groups: current.category_groups.filter((_, currentIndex) => currentIndex !== groupIndex),
    }));
  }

  function removeLine(lineId: string) {
    setLines((lines) => lines.filter((line) => line.id !== lineId));
  }

  function addLine() {
    setLines((lines) => [...lines, makeEmptyLine()]);
  }

  function addLineRelative(targetLineId: string, position: "before" | "after") {
    setLines((lines) => {
      const targetIndex = lines.findIndex((line) => line.id === targetLineId);
      if (targetIndex < 0) {
        return lines;
      }
      const insertionIndex = position === "before" ? targetIndex : targetIndex + 1;
      const next = [...lines];
      next.splice(insertionIndex, 0, makeEmptyLine());
      return next;
    });
  }

  function moveLine(lineId: string, direction: "up" | "down") {
    setLines((lines) => {
      const currentIndex = lines.findIndex((line) => line.id === lineId);
      if (currentIndex < 0) {
        return lines;
      }
      const nextIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
      if (nextIndex < 0 || nextIndex >= lines.length) {
        return lines;
      }
      return moveItem(lines, currentIndex, nextIndex);
    });
  }

  function handleDrop(targetLineId: string) {
    if (!draggedLineId || draggedLineId === targetLineId) {
      return;
    }
    setLines((lines) => {
      const fromIndex = lines.findIndex((line) => line.id === draggedLineId);
      const toIndex = lines.findIndex((line) => line.id === targetLineId);
      if (fromIndex === -1 || toIndex === -1) {
        return lines;
      }
      return moveItem(lines, fromIndex, toIndex);
    });
    setDraggedLineId(null);
  }

  function validateDraft() {
    if (!draft) {
      return "Configuração indisponível.";
    }
    const lines = draft.lines;
    const groupOwners = new Map<string, string>();
    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      if (!line.name.trim()) {
        return "Todas as linhas precisam de nome.";
      }
      if (line.show_percent && line.percent_mode === "reference_line") {
        if (!line.percent_reference_line_id) {
          return `A linha "${line.name}" precisa ter uma referencia para o percentual.`;
        }
        const percentReferenceIndex = lines.findIndex((candidate) => candidate.id === line.percent_reference_line_id);
        if (percentReferenceIndex < 0) {
          return `A linha "${line.name}" referencia uma linha invalida para percentual.`;
        }
        if (percentReferenceIndex >= index) {
          return `A linha "${line.name}" so pode usar uma linha anterior como referencia do percentual.`;
        }
      }
      if (line.line_type === "source") {
        if (!line.special_source && line.category_groups.length === 0) {
          return `A linha "${line.name}" precisa ter grupos ou uma fonte especial.`;
        }
        for (const group of line.category_groups) {
          if (!group.group_name.trim()) {
            return `A linha "${line.name}" possui um grupo sem selecao.`;
          }
          const key = group.group_name.toLocaleLowerCase();
          if (groupOwners.has(key)) {
            return `O grupo "${group.group_name}" esta repetido em mais de uma linha.`;
          }
          groupOwners.set(key, line.id);
        }
      } else {
        if (line.formula.length === 0) {
          return `A linha totalizadora "${line.name}" precisa ter formula.`;
        }
        for (const formulaItem of line.formula) {
          const referencedIndex = lines.findIndex((candidate) => candidate.id === formulaItem.referenced_line_id);
          if (referencedIndex < 0) {
            return `A linha "${line.name}" referencia uma linha inexistente.`;
          }
          if (referencedIndex >= index) {
            return `A linha "${line.name}" so pode depender de linhas anteriores.`;
          }
        }
      }
    }
    return "";
  }

  async function handleSave() {
    if (!draft) {
      setError("Configuração indisponível.");
      return;
    }
    const validationError = validateDraft();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError("");
    try {
      const response = await onSave({
        lines: normalizeOrders(draft.lines),
      });
      setDraft(response);
      onClose();
    } catch (saveError) {
      setError(parseApiError(saveError));
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="modal-card report-config-modal-card">
        <div className="report-config-modal-header">
          <div>
            <h3>Configurar {kind.toUpperCase()}</h3>
            <p>Defina a ordem das linhas, escolha grupos com busca e monte os subtotais com referencias entre linhas anteriores.</p>
          </div>
          <ModalCloseButton onClick={onClose} />
        </div>

        {loading ? (
          <div className="empty-panel">
            <p className="empty-state">Carregando configuracao...</p>
          </div>
        ) : (
          <>
            {unmappedGroups.length > 0 && (
              <div className="report-config-warning">
                <strong>Grupos ainda nao mapeados</strong>
                <div className="report-config-chip-list">
                  {unmappedGroups.map((group) => (
                    <span className="report-config-chip" key={group}>
                      {group}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {error && <div className="report-config-error">{error}</div>}

            <div className="report-config-lines-header">
              <div>
                <strong>{draft.lines.length} linhas configuradas</strong>
                <p>Use linhas agrupadoras para juntar grupos e componentes da API Linx. Use linhas totalizadoras para montar subtotais com linhas anteriores.</p>
              </div>
              <Button variant="secondary" onClick={addLine} type="button">
                Adicionar linha no fim
              </Button>
            </div>

            <div className="report-config-lines">
              {draft.lines.map((line, index) => {
                const referenceOptions = draft.lines
                  .slice(0, index)
                  .map((candidate, sourceIndex) => ({
                    value: candidate.id,
                    label: `${sourceIndex + 1}. ${candidate.name || "Linha sem nome"}`,
                  }));
                const selectedSpecialSourceOption = specialSourceOptions.find((option) => option.value === line.special_source) ?? null;
                const selectedPercentReferenceOption =
                  referenceOptions.find((option) => option.value === line.percent_reference_line_id) ?? null;
                const formulaPreview = line.formula
                  .map((formulaItem) => {
                    const referenced = lineOptions.find((option) => option.value === formulaItem.referenced_line_id);
                    if (!referenced) {
                      return null;
                    }
                    return `${formulaItem.operation === "add" ? "+" : "-"} ${referenced.label}`;
                  })
                  .filter(Boolean)
                  .join(" ");

                return (
                  <article
                    key={line.id}
                    className="report-config-line-card"
                    draggable
                    onDragOver={(event) => event.preventDefault()}
                    onDragStart={() => setDraggedLineId(line.id)}
                    onDrop={() => handleDrop(line.id)}
                  >
                    <div className="report-config-line-topbar">
                      <div className="report-config-line-title">
                        <span className="report-config-drag-handle" title="Arraste para reordenar">
                          ::
                        </span>
                        <div className="report-config-line-title-copy">
                          <strong>{line.name || `Linha ${index + 1}`}</strong>
                          <span>Linha {index + 1}</span>
                        </div>
                      </div>
                      <div className="report-config-line-actions">
                        <span className="report-config-line-badge">{line.line_type === "source" ? "Linha agrupadora" : "Linha totalizadora"}</span>
                        {!line.is_active && <span className="report-config-line-badge muted">Inativa</span>}
                        {line.is_hidden && <span className="report-config-line-badge muted">Oculta</span>}
                        <Button variant="secondary" className="compact-inline-button" disabled={index === 0} onClick={() => moveLine(line.id, "up")} type="button">
                          Subir
                        </Button>
                        <Button
                          variant="secondary"
                          className="compact-inline-button"
                          disabled={index === draft.lines.length - 1}
                          onClick={() => moveLine(line.id, "down")}
                          type="button"
                        >
                          Descer
                        </Button>
                        <Button variant="secondary" className="compact-inline-button" onClick={() => addLineRelative(line.id, "before")} type="button">
                          + Antes
                        </Button>
                        <Button variant="secondary" className="compact-inline-button" onClick={() => addLineRelative(line.id, "after")} type="button">
                          + Depois
                        </Button>
                        <Button variant="ghost" className="danger-text-action" onClick={() => removeLine(line.id)} type="button">
                          Excluir
                        </Button>
                      </div>
                    </div>

                    {line.line_type === "totalizer" && (
                      <div className="report-config-dependency-summary">
                        <strong>Formula da totalizadora</strong>
                        <span>{formulaPreview || "Escolha abaixo quais linhas anteriores entram no subtotal."}</span>
                      </div>
                    )}

                    <div className="report-config-section-grid">
                      <section className="report-config-section">
                        <div className="report-config-section-heading">
                          <strong>Identificacao</strong>
                          <span>Nome da linha, tipo e exibicao no dashboard e na tabela.</span>
                        </div>
                        <div className="form-grid wide report-config-form-grid">
                          <label className="span-two">
                            Nome da linha
                            <input value={line.name} onChange={(event) => updateLine(line.id, (current) => ({ ...current, name: event.target.value }))} />
                          </label>

                          <label>
                            Tipo da linha
                            <select
                              value={line.line_type}
                              onChange={(event) =>
                                updateLine(line.id, (current) => ({
                                  ...current,
                                  line_type: event.target.value as "source" | "totalizer",
                                  special_source: event.target.value === "totalizer" ? null : current.special_source,
                                  category_groups: event.target.value === "totalizer" ? [] : current.category_groups,
                                  formula: event.target.value === "totalizer" ? current.formula : [],
                                }))
                              }
                            >
                              <option value="source">Linha agrupadora</option>
                              <option value="totalizer">Linha totalizadora</option>
                            </select>
                          </label>

                          <div className="report-config-toggle-grid">
                            <label className="report-config-inline-toggle">
                              <input
                                checked={line.is_active}
                                onChange={(event) => updateLine(line.id, (current) => ({ ...current, is_active: event.target.checked }))}
                                type="checkbox"
                              />
                              <span>Linha ativa</span>
                            </label>

                            <label className="report-config-inline-toggle">
                              <input
                                checked={line.show_on_dashboard}
                                onChange={(event) => updateLine(line.id, (current) => ({ ...current, show_on_dashboard: event.target.checked }))}
                                type="checkbox"
                              />
                              <span>Mostrar no dashboard</span>
                            </label>

                            <label className="report-config-inline-toggle">
                              <input
                                checked={line.show_percent}
                                onChange={(event) =>
                                  updateLine(line.id, (current) => ({
                                    ...current,
                                    show_percent: event.target.checked,
                                    percent_reference_line_id: event.target.checked
                                      ? current.percent_mode === "reference_line"
                                        ? current.percent_reference_line_id
                                        : null
                                      : null,
                                  }))
                                }
                                type="checkbox"
                              />
                              <span>Mostrar percentual</span>
                            </label>

                            <label className="report-config-inline-toggle">
                              <input
                                checked={line.is_hidden}
                                onChange={(event) => updateLine(line.id, (current) => ({ ...current, is_hidden: event.target.checked }))}
                                type="checkbox"
                              />
                              <span>Ocultar na tabela</span>
                            </label>
                          </div>

                          {line.show_percent && (
                            <>
                              <label>
                                Percentual relativo a
                                <select
                                  value={line.percent_mode}
                                  onChange={(event) =>
                                    updateLine(line.id, (current) => ({
                                      ...current,
                                      percent_mode: event.target.value as "reference_line" | "grouped_children",
                                      percent_reference_line_id:
                                        event.target.value === "reference_line"
                                          ? current.percent_reference_line_id ?? referenceOptions[0]?.value ?? null
                                          : null,
                                    }))
                                  }
                                >
                                  <option value="reference_line">Outra linha anterior</option>
                                  <option value="grouped_children">Lançamentos agrupados da própria linha</option>
                                </select>
                              </label>

                              {line.percent_mode === "reference_line" && (
                                <label className="span-two">
                                  Linha de referencia
                                  <Select
                                    classNamePrefix="report-config-select"
                                    isClearable={false}
                                    isSearchable
                                    onChange={(option) =>
                                      updateLine(line.id, (current) => ({
                                        ...current,
                                        percent_reference_line_id: asSingleValue(option),
                                      }))
                                    }
                                    options={referenceOptions}
                                    placeholder="Escolha uma linha anterior"
                                    value={selectedPercentReferenceOption}
                                  />
                                </label>
                              )}
                            </>
                          )}
                        </div>
                      </section>

                      <section className="report-config-section report-config-section--wide">
                        <div className="report-config-section-heading">
                          <strong>{line.line_type === "source" ? "Composicao da linha" : "Formula da linha"}</strong>
                          <span>
                            {line.line_type === "source"
                              ? "Junte grupos/subgrupos e, se precisar, um componente da API Linx na mesma linha."
                              : "Cada linha totalizadora soma ou diminui linhas anteriores."}
                          </span>
                        </div>

                        {line.line_type === "source" ? (
                          <div className="report-config-formula-builder">
                            <div className="form-grid wide report-config-form-grid">
                              <label>
                                Operacao do componente especial
                                <select
                                  value={line.operation}
                                  onChange={(event) => updateLine(line.id, (current) => ({ ...current, operation: event.target.value as "add" | "subtract" }))}
                                >
                                  <option value="add">Soma</option>
                                  <option value="subtract">Diminui</option>
                                </select>
                                <small className="report-config-field-help">
                                  Essa operacao vale para o componente especial e tambem vira o padrao quando voce adiciona um novo grupo.
                                </small>
                              </label>

                              {specialSourceOptions.length > 0 && (
                                <label className="span-two">
                                  Componente da API Linx
                                  <Select
                                    classNamePrefix="report-config-select"
                                    isClearable
                                    isSearchable
                                    onChange={(option) =>
                                      updateLine(line.id, (current) => ({
                                        ...current,
                                        special_source: asSingleValue(option) || null,
                                      }))
                                    }
                                    options={specialSourceOptions}
                                    placeholder="Opcional. Use junto com grupos se precisar"
                                    value={selectedSpecialSourceOption}
                                  />
                                </label>
                              )}
                            </div>

                            <div className="report-config-formula-header">
                              <div>
                                <strong>Itens do agrupamento</strong>
                                <p className="report-config-inline-copy">
                                  Cada grupo ou subgrupo pode somar ou diminuir de forma independente, igual a uma linha totalizadora.
                                </p>
                              </div>
                              <Button
                                variant="secondary"
                                disabled={groupOptions.length === 0}
                                onClick={() => addGroupSelection(line.id)}
                                type="button"
                              >
                                Adicionar grupo
                              </Button>
                            </div>

                            {line.category_groups.length === 0 ? (
                              <p className="empty-state">Nenhum grupo vinculado ainda.</p>
                            ) : (
                              <div className="report-config-formula-list">
                                {line.category_groups.map((groupSelection, groupIndex) => {
                                  const selectedGroupOption = groupOptions.find((option) => option.value === groupSelection.group_name) ?? null;
                                  return (
                                    <div className="report-config-formula-row" key={`${line.id}-group-${groupIndex}`}>
                                      <label>
                                        Operacao
                                        <select
                                          value={groupSelection.operation}
                                          onChange={(event) =>
                                            updateGroupSelection(line.id, groupIndex, (currentGroup) => ({
                                              ...currentGroup,
                                              operation: event.target.value as "add" | "subtract",
                                            }))
                                          }
                                        >
                                          <option value="add">Somar</option>
                                          <option value="subtract">Diminuir</option>
                                        </select>
                                      </label>

                                      <label>
                                        Grupo ou subgrupo
                                        <Select
                                          classNamePrefix="report-config-select"
                                          isClearable={false}
                                          isSearchable
                                          onChange={(option) =>
                                            updateGroupSelection(line.id, groupIndex, (currentGroup) => ({
                                              ...currentGroup,
                                              group_name: asSingleValue(option),
                                            }))
                                          }
                                          options={groupOptions}
                                          placeholder="Busque e selecione um grupo"
                                          value={selectedGroupOption}
                                        />
                                      </label>

                                      <Button
                                        variant="ghost"
                                        className="danger-text-action"
                                        onClick={() => removeGroupSelection(line.id, groupIndex)}
                                        type="button"
                                      >
                                        Remover
                                      </Button>
                                    </div>
                                  );
                                })}
                              </div>
                            )}

                            <small className="report-config-field-help">
                              Misture entradas positivas e negativas no mesmo agrupamento sem precisar separar a linha em duas.
                            </small>
                          </div>
                        ) : (
                          <div className="report-config-formula-builder">
                            <div className="report-config-formula-header">
                              <div>
                                <strong>Linhas anteriores que entram no subtotal</strong>
                                <p className="report-config-inline-copy">A totalizadora pode usar linhas agrupadoras e totalizadoras anteriores.</p>
                              </div>
                              <Button
                                variant="secondary"
                                disabled={referenceOptions.length === 0}
                                onClick={() =>
                                  updateLine(line.id, (current) => ({
                                    ...current,
                                    formula: [...current.formula, { operation: "add", referenced_line_id: referenceOptions[0]?.value ?? "" }],
                                  }))
                                }
                                type="button"
                              >
                                Adicionar linha
                              </Button>
                            </div>

                            {line.formula.length === 0 ? (
                              <p className="empty-state">Nenhuma linha vinculada ainda.</p>
                            ) : (
                              <div className="report-config-formula-list">
                                {line.formula.map((formulaItem, formulaIndex) => {
                                  const selectedReferenceOption = referenceOptions.find((option) => option.value === formulaItem.referenced_line_id) ?? null;
                                  return (
                                    <div className="report-config-formula-row" key={`${line.id}-${formulaIndex}`}>
                                      <label>
                                        Operacao
                                        <select
                                          value={formulaItem.operation}
                                          onChange={(event) =>
                                            updateLine(line.id, (current) => ({
                                              ...current,
                                              formula: current.formula.map((item, currentIndex) =>
                                                currentIndex === formulaIndex ? { ...item, operation: event.target.value as "add" | "subtract" } : item,
                                              ),
                                            }))
                                          }
                                        >
                                          <option value="add">Somar</option>
                                          <option value="subtract">Diminuir</option>
                                        </select>
                                      </label>

                                      <label>
                                        Linha anterior
                                        <Select
                                          classNamePrefix="report-config-select"
                                          isClearable={false}
                                          isSearchable
                                          onChange={(option) =>
                                            updateLine(line.id, (current) => ({
                                              ...current,
                                              formula: current.formula.map((item, currentIndex) =>
                                                currentIndex === formulaIndex ? { ...item, referenced_line_id: asSingleValue(option) } : item,
                                              ),
                                            }))
                                          }
                                          options={referenceOptions}
                                          placeholder="Escolha uma linha anterior"
                                          value={selectedReferenceOption}
                                        />
                                      </label>

                                      <Button
                                        variant="ghost"
                                        className="danger-text-action"
                                        onClick={() =>
                                          updateLine(line.id, (current) => ({
                                            ...current,
                                            formula: current.formula.filter((_, currentIndex) => currentIndex !== formulaIndex),
                                          }))
                                        }
                                        type="button"
                                      >
                                        Remover
                                      </Button>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        )}
                      </section>
                    </div>
                  </article>
                );
              })}
            </div>

            <div className="report-config-modal-footer">
              <div className="report-config-footer-meta">
                <strong>{draft.lines.length} linhas</strong>
                <span>Voce pode arrastar, subir/descer ou inserir linha antes/depois.</span>
              </div>
              <div className="action-row">
                <Button variant="secondary" onClick={addLine} type="button">
                  Adicionar linha no fim
                </Button>
                <Button variant="ghost" onClick={onClose} type="button">
                  Cancelar
                </Button>
                <Button variant="primary" loading={saving} disabled={saving} onClick={() => void handleSave()} type="button">
                  {saving ? "Salvando..." : "Salvar configuracao"}
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
