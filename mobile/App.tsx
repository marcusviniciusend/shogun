/**
 * Shogun mobile — dashboard em tres abas: Chat, Status e Config.
 *
 * Navegacao por estado local, sem biblioteca de rotas: tres telas fixas nao
 * justificam a dependencia. Se o app crescer, este e o ponto a trocar por
 * expo-router ou react-navigation.
 */

import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { ChatScreen } from "./src/screens/ChatScreen";
import { ConfigScreen } from "./src/screens/ConfigScreen";
import { StatusScreen } from "./src/screens/StatusScreen";
import { cores, espacamento } from "./src/theme";

type Aba = "chat" | "status" | "config";

const ABAS: { id: Aba; rotulo: string }[] = [
  { id: "chat", rotulo: "Chat" },
  { id: "status", rotulo: "Status" },
  { id: "config", rotulo: "Config" },
];

export default function App() {
  const [aba, setAba] = useState<Aba>("chat");

  return (
    <SafeAreaProvider>
      <SafeAreaView style={estilos.app} edges={["top", "bottom"]}>
        <StatusBar style="light" />
        <View style={estilos.cabecalho}>
          <Text style={estilos.titulo}>Shogun</Text>
        </View>

        <View style={estilos.conteudo}>
          {aba === "chat" && <ChatScreen />}
          {aba === "status" && <StatusScreen />}
          {aba === "config" && <ConfigScreen />}
        </View>

        <View style={estilos.barraAbas}>
          {ABAS.map((item) => (
            <Pressable
              key={item.id}
              style={estilos.aba}
              onPress={() => setAba(item.id)}
            >
              <Text
                style={[
                  estilos.abaTexto,
                  aba === item.id && estilos.abaAtiva,
                ]}
              >
                {item.rotulo}
              </Text>
            </Pressable>
          ))}
        </View>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const estilos = StyleSheet.create({
  app: {
    flex: 1,
    backgroundColor: cores.fundo,
  },
  cabecalho: {
    paddingHorizontal: espacamento.m,
    paddingVertical: espacamento.s,
    borderBottomColor: cores.borda,
    borderBottomWidth: 1,
  },
  titulo: {
    color: cores.destaque,
    fontSize: 18,
    fontWeight: "700",
  },
  conteudo: {
    flex: 1,
  },
  barraAbas: {
    flexDirection: "row",
    borderTopColor: cores.borda,
    borderTopWidth: 1,
    backgroundColor: cores.superficie,
  },
  aba: {
    flex: 1,
    alignItems: "center",
    paddingVertical: espacamento.m,
  },
  abaTexto: {
    color: cores.textoFraco,
    fontWeight: "600",
  },
  abaAtiva: {
    color: cores.destaque,
  },
});
