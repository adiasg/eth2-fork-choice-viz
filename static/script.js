const margin = {top: 20, right: 90, bottom: 30, left: 90};
var graphStyle = d3.tree();
var hideLabel = false;
var clickedObject = null;
var fcDataStore = {"proto_array": {}, "total_balance": 0};
var reloadFreq = 6000;

const tooltipDiv = d3.select("body").append("div")
            .attr("class", "tooltip")
            .style("opacity", 1e-6);

const infoDiv = d3.select("#info-box");

function getColor(value) {
  // value from 0 to 1
  var hue = (value * 120).toString(10);
  return ["hsl(", hue, ",60%,50%)"].join("");
}

function drawSvg(fcData) {
  var treeData = fcData.proto_array;
  var totalBalance = fcData.total_balance;
  fcDataStore = fcData;
  d3.select("#d3-svg").remove();
  d3.selectAll(".tooltip-span").remove();

  document.getElementById("current-slot").textContent = fcData.current_slot;
  document.getElementById("current-epoch").textContent = Math.floor(fcData.current_slot/32);
  document.getElementById("finalized-epoch").textContent = fcData.finality_checkpoints.finalized.epoch;
  document.getElementById("justified-epoch").textContent = fcData.finality_checkpoints.current_justified.epoch;
  document.getElementById("head-root").textContent = fcData.current_head.root;
  document.getElementById("finalized-root").textContent = fcData.finality_checkpoints.finalized.root;
  document.getElementById("justified-root").textContent = fcData.finality_checkpoints.current_justified.root;

  var width  = window.innerWidth - margin.left - margin.right,
      height = 0.85*window.innerHeight - margin.top - margin.bottom;

  const treemap = graphStyle.size([height, width]);
  nodes = d3.hierarchy(treeData, d => d.children);
  nodes = treemap(nodes);

  const svg = d3.select("#svg-box").append("svg").attr("class", "main-svg").attr("id", "d3-svg"),
        drawing = svg.append("g"),
        g = drawing.append("g"),
        zoomChild = svg.append("g");
  // svg.attr("width", "100%")
  //   .attr("height", "100%"),
  g.attr("transform",
        "translate(" + margin.left + "," + margin.top + ")");

  var zoom = d3.zoom().scaleExtent([0.1, 4]).on("zoom", (event, d) => {
    drawing.attr("transform", event.transform)
  });
  svg.call(zoom);
  document.getElementById("reset").onclick = () => {
    svg.call(zoom.transform, d3.zoomIdentity.translate(0,0).scale(1));
  };

  // adds the links between the nodes
  const link = g.selectAll(".link")
    .data( nodes.descendants().slice(1))
    .enter().append("path")
    .attr("class", d => d.data.path=="canonical" ? "tree-link tree-link-canonical" : "tree-link")
    .attr("d", d => {
       return "M" + d.y + "," + d.x
         + "C" + (d.y + d.parent.y) / 2 + "," + d.x
         + " " + (d.y + d.parent.y) / 2 + "," + d.parent.x
         + " " + d.parent.y + "," + d.parent.x;
       });

  function getNodeStatus(d) {
    return (d.data.status == "final" ? "Final" : (d.data.status == "justified" ? "Best Just." : "Pending"))
  }

  function nodeClick(event, d) {
    var this_node = d3.select(this);
    infoDiv.html("");
    infoDiv.transition()
      .duration(300)
      .style("opacity", 1);
    infoDiv
          .append('div').attr("class", "d-flex flex-column").text("Block Root: " + d.data.root)
          .append('div').attr("class", "d-flex flex-column").text("Slot: " + d.data.slot)
          .append('div').attr("class", "d-flex flex-column").text("Epoch: " + Math.floor(d.data.slot/32))
          .append('div').attr("class", "d-flex flex-column").text("Status: " + getNodeStatus(d))
          .append('div').attr("class", "d-flex flex-column").text("Supporting Percentage: " + (100*d.data.weight/totalBalance).toFixed(2) + "%")
          .append('div').attr("class", "d-flex flex-column").text("Supporting Stake: " + d.data.weight + " ETH");
    this_node.raise();
    clickedObject = d3.select(this);
  }

  function nodeMouseOver(event, d) {
    var this_node = d3.select(this);
    tooltipDiv.transition()
      .duration(300)
      .style("opacity", 1);
    tooltipDiv.append('span').attr("class", "tooltip-span")
            .text("Slot: " + d.data.slot)
            .append('span').attr("class", "tooltip-span")
            .text("Epoch: " + Math.floor(d.data.slot/32))
            .append('span').attr("class", "tooltip-span")
            .text("Support: " + (100*d.data.weight/totalBalance).toFixed(2) + "%")
            .append('span').attr("class", "tooltip-span")
            .text("Status: " + getNodeStatus(d));
    this_node.raise();
  }

  function nodeMouseMove(event, d) {
    tooltipDiv.style("left", (event.pageX ) + "px")
              .style("top", (event.pageY) + "px");
  }

  function nodeMouseOut(event, d) {
    var this_node = d3.select(this);
    tooltipDiv.transition()
      .duration(300)
      .style("opacity", 1e-6);
    d3.selectAll(".tooltip-span").remove();
    node.raise();
    if(clickedObject) {
      clickedObject.raise();
    }
  }

  const node = g.selectAll(".node")
      .data(nodes.descendants())
      .enter().append("g")
      .attr("class", d => "node " + (d.children ? "node-internal " : "node-leaf ") + (d.data.index == 0 ? "node-root" : "node-non-root"))
      .attr("transform", d => "translate(" + d.y + "," + d.x + ")")
      .on("click", nodeClick)
      .on("mouseover", nodeMouseOver)
      .on("mousemove", nodeMouseMove)
      .on("mouseout", nodeMouseOut);

  function nodeWidth(d) {
    return Math.max(1, Math.floor(Math.log10(d.data.slot)));
  }

  const nodeHeight = 1.5;

  node.append("rect")
    .attr("class", d => (d.data.index == 0 ? "node-root" : "node-non-root") + " node-" + d.data.status )
    .attr("width", d => nodeWidth(d)+"em")
    .attr("height", nodeHeight+"em")
    .attr("x", d => -nodeWidth(d)/2+"em")
    .attr("y", d => -nodeHeight/2+"em")
    .style("fill", d => getColor(d.data.weight/totalBalance));

    if(!hideLabel) {
      node.append("text")
        .attr("class", "node-label")
        .attr("x", d => -nodeWidth(d)/2+"em")
        .attr("y", nodeHeight/4+"em")
        .text(d => d.data.slot);
    }

}


function loadSvg() {
  fetch(window.location.href+"data")
    .then(response => {
      if(response.status != 200) {
        console.log("GET " + window.location.href+"data" + " returned status: " + response.status + " and text: " + response.text());
        treeData = {};
        totalBalance = 0;
      }
      return fc_data = response.json();
    })
    .then(fc_data => {
      if(typeof fc_data !== 'undefined') {
        return fc_data;
      }
      return {"proto_array": {}, "total_balance": 0};
    })
    .then(fc_data => drawSvg(fc_data))
    .catch(err => {
      console.log("fetch(\"" + window.location.href+"data\") failed with error: " + err);
    });
}

loadSvg();
var reloader = window.setInterval(loadSvg, reloadFreq);

document.getElementById("toggle-label").onclick = () => {
  hideLabel = !hideLabel;
  drawSvg(fcDataStore);
};

document.getElementById("redraw-tree").onclick = () => {
  graphStyle = d3.tree();
  drawSvg(fcDataStore);
};

document.getElementById("redraw-cluster").onclick = () => {
  graphStyle = d3.cluster();
  drawSvg(fcDataStore);
};

document.getElementById("auto-reload").onclick = () => {
  button = document.getElementById("auto-reload");
  if(reloader==0){
    button.className = "palette-button-enabled";
    loadSvg();
    reloader = window.setInterval(loadSvg, reloadFreq);
  }
  else {
    button.className = "palette-button";
    window.clearInterval(reloader);
    reloader = 0;
  }
};

function onResize() {
  drawSvg(fcDataStore);
}
