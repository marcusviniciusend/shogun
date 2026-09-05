/** Banner de erro visivel — todo erro de API aparece por aqui, nunca some em log. */

import { StyleSheet, Text, View } from "react-native";

import { cores, espacamento } from "../theme";

export function Aviso({ mensagem }: { mensagem: string }) {
  return (
    <View style={estilos.caixa}>
      <Text style={estilos.texto}>{mensagem}</Text>
    </View>
  );
}

const estilos = StyleSheet.create({
  caixa: {
    backgroundColor: cores.erroFundo,
    borderColor: cores.erroBorda,
    borderWidth: 1,
    borderRadius: 8,
    padding: espacamento.m,
    marginBottom: espacamento.m,
  },
  texto: {
    color: cores.erroTexto,
  },
});
