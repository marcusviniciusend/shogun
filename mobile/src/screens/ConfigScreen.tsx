/**
 * Configuracao do servidor — URL e token, guardados so no aparelho
 * (AsyncStorage). Nada vem hardcoded: sem configurar aqui, as outras telas
 * orientam o usuario a preencher.
 */

import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { ApiError, verificarSaude } from "../api";
import { Aviso } from "../components/Aviso";
import { carregarConfig, salvarConfig } from "../storage";
import { cores, espacamento } from "../theme";

export function ConfigScreen() {
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    carregarConfig().then((config) => {
      setUrl(config.url);
      setToken(config.token);
    });
  }, []);

  async function salvar() {
    setErro(null);
    setAviso(null);
    if (!url.trim()) {
      setErro("Informe a URL do servidor antes de salvar.");
      return;
    }
    await salvarConfig({ url, token });
    setAviso("Configuracao salva.");
  }

  async function testarConexao() {
    if (ocupado) return;
    setErro(null);
    setAviso(null);
    setOcupado(true);
    try {
      await verificarSaude({ url, token });
      setAviso("Servidor respondeu ao /health — conexao ok.");
    } catch (excecao) {
      setErro(
        excecao instanceof ApiError
          ? excecao.message
          : "Nao consegui testar a conexao."
      );
    } finally {
      setOcupado(false);
    }
  }

  return (
    <ScrollView style={estilos.tela} contentContainerStyle={estilos.conteudo}>
      <Text style={estilos.rotulo}>URL do servidor</Text>
      <Text style={estilos.dica}>
        IP Tailscale do PC onde o servidor roda, com a porta — ex.:
        http://100.x.x.x:8000. Descubra com `tailscale ip -4` no PC.
      </Text>
      <TextInput
        style={estilos.campo}
        value={url}
        onChangeText={setUrl}
        placeholder="http://100.x.x.x:8000 (IP Tailscale do PC)"
        placeholderTextColor={cores.textoFraco}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
      />

      <Text style={estilos.rotulo}>Token de acesso</Text>
      <Text style={estilos.dica}>
        O mesmo valor de SHOGUN_AUTH_TOKEN do servidor. Fica salvo apenas neste
        aparelho.
      </Text>
      <TextInput
        style={estilos.campo}
        value={token}
        onChangeText={setToken}
        placeholder="SHOGUN_AUTH_TOKEN"
        placeholderTextColor={cores.textoFraco}
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
      />

      {erro && <Aviso mensagem={erro} />}
      {aviso && (
        <View style={estilos.caixaOk}>
          <Text style={estilos.textoOk}>{aviso}</Text>
        </View>
      )}

      <View style={estilos.botoes}>
        <Pressable style={estilos.botao} onPress={salvar}>
          <Text style={estilos.botaoTexto}>Salvar</Text>
        </Pressable>
        <Pressable
          style={[estilos.botaoSecundario, ocupado && estilos.botaoDesabilitado]}
          onPress={testarConexao}
          disabled={ocupado}
        >
          {ocupado ? (
            <ActivityIndicator color={cores.texto} />
          ) : (
            <Text style={estilos.botaoSecundarioTexto}>Testar conexao</Text>
          )}
        </Pressable>
      </View>
    </ScrollView>
  );
}

const estilos = StyleSheet.create({
  tela: {
    flex: 1,
  },
  conteudo: {
    padding: espacamento.m,
  },
  rotulo: {
    color: cores.texto,
    fontWeight: "600",
    marginTop: espacamento.m,
  },
  dica: {
    color: cores.textoFraco,
    fontSize: 12,
    marginTop: 2,
    marginBottom: espacamento.s,
  },
  campo: {
    backgroundColor: cores.superficie,
    borderColor: cores.borda,
    borderWidth: 1,
    borderRadius: 8,
    color: cores.texto,
    paddingHorizontal: espacamento.m,
    paddingVertical: espacamento.s + 2,
    marginBottom: espacamento.s,
  },
  caixaOk: {
    borderColor: cores.ok,
    borderWidth: 1,
    borderRadius: 8,
    padding: espacamento.m,
    marginTop: espacamento.s,
  },
  textoOk: {
    color: cores.ok,
  },
  botoes: {
    flexDirection: "row",
    gap: espacamento.m,
    marginTop: espacamento.g,
  },
  botao: {
    flex: 1,
    backgroundColor: cores.destaque,
    borderRadius: 8,
    padding: espacamento.m,
    alignItems: "center",
  },
  botaoTexto: {
    color: cores.fundo,
    fontWeight: "600",
  },
  botaoSecundario: {
    flex: 1,
    borderColor: cores.borda,
    borderWidth: 1,
    borderRadius: 8,
    padding: espacamento.m,
    alignItems: "center",
  },
  botaoSecundarioTexto: {
    color: cores.texto,
    fontWeight: "600",
  },
  botaoDesabilitado: {
    opacity: 0.6,
  },
});
