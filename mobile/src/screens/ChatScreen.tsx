/**
 * Chat com o Shogun.
 *
 * O `session_id` e persistido localmente: a primeira mensagem vai sem id, o
 * servidor cria a sessao e o id devolvido e guardado e reenviado nas proximas —
 * mesma logica do cliente desktop. O historico exibido tambem fica no aparelho,
 * para a conversa nao zerar a cada abertura do app.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { ApiError, enviarComando } from "../api";
import { Aviso } from "../components/Aviso";
import { carregarConfig, carregarSessao, salvarSessao } from "../storage";
import { cores, espacamento } from "../theme";

interface Mensagem {
  id: string;
  autor: "usuario" | "shogun";
  texto: string;
}

const CHAVE_HISTORICO = "shogun/chatHistorico";
const HISTORICO_MAX = 100;

export function ChatScreen() {
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [rascunho, setRascunho] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const proximoId = useRef(0);

  useEffect(() => {
    AsyncStorage.getItem(CHAVE_HISTORICO).then((bruto) => {
      if (!bruto) return;
      try {
        const salvas = JSON.parse(bruto) as Mensagem[];
        setMensagens(salvas);
        proximoId.current = salvas.length;
      } catch {
        // historico corrompido: descarta em vez de travar o chat
        AsyncStorage.removeItem(CHAVE_HISTORICO);
      }
    });
  }, []);

  function anexar(anteriores: Mensagem[], nova: Omit<Mensagem, "id">): Mensagem[] {
    const todas = [
      ...anteriores,
      { ...nova, id: String(proximoId.current++) },
    ].slice(-HISTORICO_MAX);
    AsyncStorage.setItem(CHAVE_HISTORICO, JSON.stringify(todas)).catch(() => {});
    return todas;
  }

  async function enviar() {
    const texto = rascunho.trim();
    if (!texto || enviando) return;

    setErro(null);
    setRascunho("");
    setEnviando(true);
    setMensagens((m) => anexar(m, { autor: "usuario", texto }));

    try {
      const config = await carregarConfig();
      const sessionId = await carregarSessao("chat");
      const resposta = await enviarComando(config, sessionId, texto);
      await salvarSessao("chat", resposta.session_id);
      setMensagens((m) => anexar(m, { autor: "shogun", texto: resposta.text }));
    } catch (excecao) {
      setErro(
        excecao instanceof ApiError
          ? excecao.message
          : "Algo deu errado ao enviar o comando."
      );
      // devolve o texto ao campo para o usuario nao redigitar
      setRascunho(texto);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={estilos.tela}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <FlatList
        style={estilos.lista}
        contentContainerStyle={estilos.listaConteudo}
        data={[...mensagens].reverse()}
        inverted
        keyExtractor={(m) => m.id}
        renderItem={({ item }) => (
          <View
            style={[
              estilos.balao,
              item.autor === "usuario" ? estilos.balaoUsuario : estilos.balaoShogun,
            ]}
          >
            <Text
              style={
                item.autor === "usuario"
                  ? estilos.balaoTextoUsuario
                  : estilos.balaoTexto
              }
            >
              {item.texto}
            </Text>
          </View>
        )}
        ListEmptyComponent={
          <Text style={estilos.vazio}>
            Mande um comando para o Shogun. A sessao continua de onde parou.
          </Text>
        }
      />

      {erro && <Aviso mensagem={erro} />}

      <View style={estilos.rodape}>
        <TextInput
          style={estilos.campo}
          value={rascunho}
          onChangeText={setRascunho}
          placeholder="Fale com o Shogun..."
          placeholderTextColor={cores.textoFraco}
          editable={!enviando}
          onSubmitEditing={enviar}
          returnKeyType="send"
          multiline
        />
        <Pressable
          style={[estilos.botao, enviando && estilos.botaoDesabilitado]}
          onPress={enviar}
          disabled={enviando}
        >
          {enviando ? (
            <ActivityIndicator color={cores.fundo} />
          ) : (
            <Text style={estilos.botaoTexto}>Enviar</Text>
          )}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const estilos = StyleSheet.create({
  tela: {
    flex: 1,
    padding: espacamento.m,
  },
  lista: {
    flex: 1,
  },
  listaConteudo: {
    paddingVertical: espacamento.s,
  },
  vazio: {
    color: cores.textoFraco,
    textAlign: "center",
    // a lista e invertida, entao o texto de vazio tambem chega invertido
    transform: [{ scaleY: -1 }],
    padding: espacamento.g,
  },
  balao: {
    maxWidth: "85%",
    borderRadius: 12,
    padding: espacamento.m,
    marginVertical: espacamento.s,
  },
  balaoUsuario: {
    alignSelf: "flex-end",
    backgroundColor: cores.destaque,
  },
  balaoShogun: {
    alignSelf: "flex-start",
    backgroundColor: cores.superficie,
    borderColor: cores.borda,
    borderWidth: 1,
  },
  balaoTexto: {
    color: cores.texto,
  },
  balaoTextoUsuario: {
    color: cores.fundo,
  },
  rodape: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: espacamento.s,
  },
  campo: {
    flex: 1,
    backgroundColor: cores.superficie,
    borderColor: cores.borda,
    borderWidth: 1,
    borderRadius: 8,
    color: cores.texto,
    paddingHorizontal: espacamento.m,
    paddingVertical: espacamento.s + 2,
    maxHeight: 120,
  },
  botao: {
    backgroundColor: cores.destaque,
    borderRadius: 8,
    paddingHorizontal: espacamento.g,
    paddingVertical: espacamento.m,
  },
  botaoDesabilitado: {
    opacity: 0.6,
  },
  botaoTexto: {
    color: cores.fundo,
    fontWeight: "600",
  },
});
