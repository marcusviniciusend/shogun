/**
 * Status dos agentes — a acao `consultar_pendencias` do servidor.
 *
 * Nao existe endpoint dedicado: o cliente envia um comando de texto ao
 * `POST /comando` e o LLM roteia para a acao. A tela usa uma sessao propria
 * (persistida separada da do chat) para nao poluir o historico da conversa.
 */

import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { ApiError, enviarComando } from "../api";
import { Aviso } from "../components/Aviso";
import { AgentAction } from "../contracts";
import { carregarConfig, carregarSessao, salvarSessao } from "../storage";
import { cores, espacamento } from "../theme";

const COMANDO_PENDENCIAS = "Quais sao as pendencias dos agentes?";

export function StatusScreen() {
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resumo, setResumo] = useState<string | null>(null);
  const [acoes, setAcoes] = useState<AgentAction[]>([]);

  const atualizar = useCallback(async () => {
    if (carregando) return;
    setCarregando(true);
    setErro(null);
    try {
      const config = await carregarConfig();
      const sessionId = await carregarSessao("status");
      const resposta = await enviarComando(
        config,
        sessionId,
        COMANDO_PENDENCIAS
      );
      await salvarSessao("status", resposta.session_id);
      setResumo(resposta.text);
      setAcoes(resposta.actions);
    } catch (excecao) {
      setErro(
        excecao instanceof ApiError
          ? excecao.message
          : "Algo deu errado ao consultar as pendencias."
      );
    } finally {
      setCarregando(false);
    }
  }, [carregando]);

  return (
    <ScrollView style={estilos.tela} contentContainerStyle={estilos.conteudo}>
      <Pressable
        style={[estilos.botao, carregando && estilos.botaoDesabilitado]}
        onPress={atualizar}
        disabled={carregando}
      >
        {carregando ? (
          <ActivityIndicator color={cores.fundo} />
        ) : (
          <Text style={estilos.botaoTexto}>Consultar pendencias</Text>
        )}
      </Pressable>

      {erro && <Aviso mensagem={erro} />}

      {resumo !== null && !erro && (
        <View style={estilos.cartao}>
          <Text style={estilos.resumo}>{resumo}</Text>
        </View>
      )}

      {acoes.map((acao, indice) => (
        <View key={indice} style={estilos.cartao}>
          <View style={estilos.linhaAgente}>
            <Text style={estilos.agente}>{acao.agent}</Text>
            <Text
              style={[
                estilos.chip,
                acao.status === "ok" ? estilos.chipOk : estilos.chipErro,
              ]}
            >
              {acao.status}
            </Text>
          </View>
          {acao.detail ? (
            <Text style={estilos.detalhe}>{acao.detail}</Text>
          ) : null}
        </View>
      ))}

      {resumo === null && !erro && !carregando && (
        <Text style={estilos.vazio}>
          Toque em consultar para ver o que os agentes tem pendente.
        </Text>
      )}
    </ScrollView>
  );
}

const estilos = StyleSheet.create({
  tela: {
    flex: 1,
  },
  conteudo: {
    padding: espacamento.m,
    gap: espacamento.m,
  },
  botao: {
    backgroundColor: cores.destaque,
    borderRadius: 8,
    padding: espacamento.m,
    alignItems: "center",
  },
  botaoDesabilitado: {
    opacity: 0.6,
  },
  botaoTexto: {
    color: cores.fundo,
    fontWeight: "600",
  },
  cartao: {
    backgroundColor: cores.superficie,
    borderColor: cores.borda,
    borderWidth: 1,
    borderRadius: 12,
    padding: espacamento.m,
  },
  resumo: {
    color: cores.texto,
    lineHeight: 20,
  },
  linhaAgente: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  agente: {
    color: cores.texto,
    fontWeight: "600",
  },
  chip: {
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  chipOk: {
    color: cores.ok,
  },
  chipErro: {
    color: cores.falha,
  },
  detalhe: {
    color: cores.textoFraco,
    marginTop: espacamento.s,
  },
  vazio: {
    color: cores.textoFraco,
    textAlign: "center",
    padding: espacamento.g,
  },
});
