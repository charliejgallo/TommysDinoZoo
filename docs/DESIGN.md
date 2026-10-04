# Tommy's Dino Zoo — documento de diseño

Un Jurassic Park en miniatura que salió bien: Tommy cuida una granjita con
dinosaurios tiernos. Para chicos de 5 a 15 años o para jugar relajado.
**No se puede perder**: ningún dino se muere ni se escapa, no hay vidas ni
reloj que castigue. Lo peor que pasa es que un dino quede tristón hasta que
lo mimen.

Decisiones cerradas con Charlie (2026-10-04): Godot 4, 3D real; cámara 3/4
que sigue a Tommy (arriba = adelante, sin giro); día de juego de 20 min
ajustable de 15 a 90 en Ajustes; al final del día Tommy se va a dormir;
un jugador con el código listo para dos; dinos que llegan como huevos;
castellano + inglés con packs de idioma; teclas de abajo.

## 1. Controles

| | Teclado | Joystick |
|---|---|---|
| Caminar | flechas o WASD | palanca izquierda / cruz |
| **A** Acción (según contexto) | Z, Espacio o Enter | A (Xbox) / ✕ (PlayStation) |
| **B** Cambiar casillero · mantener = soltar | X | B / ◯ |
| Menú (pausa, mochila, mapa, ajustes) | Esc | Start / Options |

Correr: mantener la palanca a fondo o la flecha más de un segundo (sin
tecla). Nada de combinaciones: un chico de 5 años juega con flechas y dos
botones.

**A** hace lo más útil de lo que tiene adelante, siempre mostrado con un
cartelito (icono + palabra) arriba del objetivo antes de apretar:
- frente a un dino: dar lo que tengo en la mano si le sirve (comida, cepillo,
  pelota), si no **acariciar**;
- frente a una cosa suelta en el suelo: **agarrar** (va al casillero activo
  si está vacío, si no al primero libre; si los tres están llenos, avisa);
- frente a una planta madura / árbol: **cosechar** / **sacudir**;
- frente a una parcela vacía con semilla en mano: **plantar**; con regadera:
  **regar**;
- frente a una persona: **hablar** (misiones);
- frente a la incubadora con un huevo: **poner el huevo**;
- frente a un comedero/bebedero: **llenar** con lo que tengo;
- con un mueble/cartel empaquetado en la mano y nada adelante: **ubicar**
  (aparece la silueta en la grilla antes);
- caca de dino: **juntar** con la pala (o pide la pala si no la tenés).

**B** pasa al casillero siguiente (1 → 2 → 3 → 1); mantener medio segundo
suelta lo del casillero activo adelante de Tommy.

## 2. Inventario

Tres casilleros abajo en la pantalla, el activo resaltado. Tommy lleva en la
mano lo del casillero activo (se ve el objeto en 3D). Hay un **baúl** en la
casa y **cajones** que se pueden comprar y poner en la granja para guardar
más (A con un objeto en la mano = guardar; A con la mano vacía = abrir la
lista y elegir). Las herramientas también ocupan casillero: decidir qué
llevar es parte del juego.

## 3. El día

- Duración configurable (15, 20, 30, 45, 60, 90 min; 20 por defecto).
- Amanecer → día → atardecer → noche (cielo, luz, sombras largas, faroles).
- A los 3/4 del día: sol naranja y un aviso suave ("Se está haciendo de
  noche"). Los dinos bostezan y van a sus camas/nidos.
- Al terminar: Tommy bosteza y la pantalla funde a la casita; se guarda solo.
  **Resumen del día**: dinos felices, monedas ganadas, misiones cumplidas,
  bebés que crecieron, algo lindo que pasó ("Trici jugó con la pelota 5
  veces"). Pantalla "¡Hasta mañana!" con Tommy durmiendo. Para seguir hay que
  apretar A (y "Salir" está ahí mismo): corte natural de sesión para los
  padres.
- Cada día nuevo trae misiones nuevas, cosechas maduras, huevos que nacen y
  bebés que crecen.

## 4. Dinosaurios

Caricatura 3D tierna como los de Monster Hop: cabeza grande, ojos grandes
con brillo, cuerpo redondo, patitas cortas, colores pastel con manchas o
rayas. Todos con nombre de especie real y un **dato real** para el álbum.

| # | Especie | Hábitat | Come | Personalidad / gracia |
|---|---|---|---|---|
| 1 | Triceratops | Pradera | helechos, zapallos | empuja la pelota con los cuernos |
| 2 | Estegosaurio | Pradera | helechos, hojas | las placas cambian de color cuando está feliz |
| 3 | Anquilosaurio | Cañón | bayas, raíces | se hace bolita cuando le hacen cosquillas |
| 4 | Braquiosaurio | Bosque alto | hojas de árbol | baja el cuello para que Tommy lo acaricie |
| 5 | Parasaurolofo | Laguna | plantas de agua | toca "música" con la cresta |
| 6 | Paquicefalosaurio | Cañón | bayas, frutas | da cabezazos suaves a la pelota |
| 7 | Iguanodonte | Bosque | hojas, frutas | saluda con el pulgar |
| 8 | Protoceratops | Cañón | semillas, raíces | cava pozos y encuentra cosas |
| 9 | Gallimimus | Pradera | frutas, bichitos | corre carreras con Tommy |
| 10 | Therizinosaurio | Bosque | hojas | peludito, rasca la espalda contra los árboles |
| 11 | Tiranosaurio Rex | Valle Rex | croquetas de carne | grandote mimoso, bracitos cortos que aplauden |
| 12 | Velociraptor | Pradera | croquetas, pescado | juega como un cachorro, trae la pelota |
| 13 | Espinosaurio | Laguna | pescado | pesca solo y le regala pescados a Tommy |
| 14 | Dilofosaurio | Bosque | croquetas, bichitos | abre la gola cuando está contento |
| 15 | Carnotauro | Valle Rex | croquetas | corre a toda velocidad y frena de cola |
| 16 | Compsognathus | Pradera | bichitos, croquetas | anda en grupito de 3, siguen a Tommy |
| 17 | Microraptor | Bosque | bichitos | planea de árbol en árbol |
| 18 | Pteranodon | Acantilado | pescado | lleva cosas volando |
| 19 | Arqueoptérix | Acantilado | bichitos, bayas | canta al amanecer |
| 20 | Plesiosaurio (primo marino) | Laguna | pescado | lleva a Tommy a dar una vuelta por el agua |

Los tamaños se miniaturizan para que entren en una granjita (Tommy = 1 m):
compi 0,35 m, raptor 0,9, triceratops 1,4 de alto, rex 2,4, braquio 4.

### Necesidades (sin castigo)
Cuatro barritas que se ven al acercarse (con iconos, sin números):
- **Panza** (comida correcta en el comedero o en la mano),
- **Limpieza** (cepillo, baño con la manguera/balde, juntar las cacas del hábitat),
- **Juego** (pelota, juguetes, acariciar, correr),
- **Cariño** (acariciar, hablar, regalitos, su comida favorita).

Bajan despacio con el día. Un dino con todo bien muestra corazones, juega
solo y "regala" cosas (un pescado, una piedra brillante, una pluma).
Uno descuidado se sienta tristón con una nubecita; nunca se enferma ni se
va. Además cada hábitat tiene **comodidad** (plantas que le gustan, agua,
juguetes, refugio) que sube el ánimo.

### Crecimiento
Huevo (1 día en la incubadora) → bebé (2 días) → joven (3 días) → adulto.
Un día cuenta para crecer si terminó con el dino contento; si no, no
retrocede, simplemente espera. Al nacer, el chico **le pone nombre**
(con sugerencias para los que todavía no escriben).

### Amistad
Cada dino tiene un nivel de amistad (0-5 corazones) que sube con cada
mimo. A más corazones: trucos nuevos (sentarse, dar la pata, rodar, montar
para los grandes), y su ficha del álbum se va completando.

## 5. La granja y los hábitats

Un mapa único que se agranda comprando terrenos. Arriba en pantalla = norte.

- **La Granjita** (inicio): casa de Tommy (cama = terminar el día antes,
  baúl, guardarropa), huerta, incubadora, tablero de misiones, tiendita.
- **Pradera** (abierta al inicio, con el primer huevo: Triceratops).
- **Bosque alto**, **Laguna**, **Cañón**, **Acantilado** (pajarera),
  **Valle Rex**: se compran como terrenos nuevos con monedas.
- Los hábitats se cercan solos; adentro el chico decora libremente.

Grilla de 1 m para ubicar cosas: cercas, comederos, bebederos, nidos,
juguetes, plantas, caminitos, faroles, bancos, carteles, flores. Todo se
puede volver a levantar (A con la mano libre sobre el objeto → vuelve
empaquetado).

## 6. Huerta y plantas

Parcelas de tierra donde se plantan semillas compradas o encontradas:
helechos, bayas, zapallos, sandías, zanahorias, flores. Regar una vez por
día → crece en 1-3 días → cosechar. Árboles frutales (manzano, palmera de
cocos, árbol de hojas para el braquio) que se sacuden. Arbustos de bayas
silvestres que vuelven a dar cada día. El estanque da pescado con la caña.

## 7. Misiones y monedas

- **Tablero de misiones**: 3 misiones por día, cortas y claras
  ("Dale 3 helechos a Trici", "Juntá 5 cacas en la pradera", "Plantá
  zanahorias", "Cepillá a un dino", "Sacale una foto al braquio").
- **Pedidos de vecinos** que pasean por la granja (la doctora Ana —
  paleontóloga que vende huevos—, el abuelo Tito —tiendita— y chicos
  visitantes): "¿Me mostrás un dino que vuele?", "Necesito 4 bayas".
- **Visitantes**: cuantos más dinos felices, más visitantes, y dejan
  monedas en la alcancía de la entrada (ingreso tranquilo para los más
  chicos que sólo quieren mimar dinos).
- **Hitos** (trofeos): primer huevo, 10 dinos, todas las especies de un
  hábitat, amistad máxima, etc.
- Sin tiempo límite: las misiones del tablero duran el día; los pedidos de
  vecinos esperan lo que haga falta.

## 8. Tienda

Semillas, comida, herramientas (regadera, cepillo, pala, pelota, caña,
cámara de fotos, manguera), **huevos** (los vende la doctora Ana; algunas
especies se habilitan con hitos o con el terreno de su hábitat), muebles y
decoración, terrenos, y **ropa para Tommy** (gorras, remeras, mochilas,
como en Monster Hop; piel y pelo gratis).

## 9. Álbum

Una ficha por especie con su foto (la que sacó el chico con la cámara), el
dato real, lo que le gusta comer, su hábitat y los trucos aprendidos.
Educativo sin ser escuela.

## 10. Accesibilidad para los más chicos

- Todo con iconos; los textos se pueden leer en voz (opción futura).
- Cartelito de acción siempre visible antes de apretar A.
- Flecha suave que señala hacia la misión elegida (se puede apagar).
- Nada de apuro, nada de fallar; los errores no existen (si das comida
  equivocada, el dino la huele y dice "mmm, no").

## 11. Ajustes

Duración del día (15-90 min), idioma, volumen de música/efectos, flecha
guía, tamaño del texto, pantalla completa, controles (ver/remapear),
**y una sección para padres** con el tiempo jugado hoy.

## 12. Expansiones (arquitectura)

Todo el contenido es **datos**: `content/<paquete>/pack.json` lista dinos,
objetos, plantas, hábitats, misiones, muebles, ropa y textos, cada uno con
su id de texto (`dino.trike`, `item.fern`, `habitat.meadow`) y su modelo
`.glb`. El juego base es el paquete `base`; una expansión ("Era del Hielo"
con mamuts y tigres dientes de sable, "Fondo del mar", "Navidad en la
granja") es otra carpeta con su `pack.json`, sus modelos y sus textos.

- **Idiomas**: un archivo `.po` por idioma y paquete (`lang/es.po`,
  `lang/en.po`); un idioma nuevo = agregar archivos `xx.po`, el menú lo
  detecta solo. También se leen de `user://lang/` para packs sin recompilar.
- **Guardado**: JSON versionado en `user://saves/`, tres ranuras; todo por
  id de texto, así que agregar contenido no rompe partidas viejas.
- **Dos jugadores**: el jugador es un nodo con su dispositivo de entrada y
  su inventario; la cámara encuadra al grupo. Sumar el segundo es activar
  otro nodo, no reescribir el juego.

## 13. Lo técnico

- Godot 4.7 (Forward+; Metal en Mac, Vulkan/D3D12 en Windows), GDScript,
  escenas como texto.
- Modelos procedurales en Blender (`art/blender/`, scripts de Python) →
  `.glb` con esqueleto y acciones. Sin texturas: colores planos por rol de
  material + sombreado propio (suave, tipo plastilina, con borde oscuro en
  los costados) para que todo combine.
- CI de GitHub Actions exporta `.app` universal y `.exe`.
- Herramientas de desarrollo: `--shot=<png>` captura y sale, `--scene=` abre
  una escena directo (para las capturas y pruebas automáticas).

## 14. Plan

1. **Muestra de estilo** (esto que sigue): Tommy con sus animaciones,
   triceratops bebé y adulto, braquiosaurio, raptor y rex, un pedacito de
   pradera con cerca, árboles, comedero, huevo e incubadora, la cámara 3/4,
   el HUD de 3 casilleros. Charlie aprueba el estilo.
2. Núcleo jugable: caminar, agarrar/soltar, dar de comer, acariciar,
   necesidades, día/noche, dormir, guardar, una misión.
3. Todo el arte (20 dinos × 3 edades, plantas, muebles, herramientas,
   hábitats, NPCs) con agentes en paralelo.
4. Sistemas completos: huerta, incubadora/crecimiento, tienda, terrenos,
   decorar, misiones, visitantes, álbum, ropa, música y efectos.
5. Pulido, idiomas, CI, publicación.
