// Formal environment for uart_tx (tools/formal, closure_core/formal.py).
// Hand-reviewed: these assumptions define the legal stimulus the formal
// search may use. Formal only measures (witness depth, reachability);
// Verilator alone decides reward and every gate.
//
// Input names equal uart_tx's port names, so a witness converts directly into
// a testbench that drives the DUT through its ports.
module formal_tx (
  input wire        clk,
  input wire        rst,
  input wire [7:0]  s_axis_tdata,
  input wire        s_axis_tvalid,
  input wire [15:0] prescale
);
  wire s_axis_tready, txd, busy;

  uart_tx dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
    .txd(txd), .busy(busy),
    .prescale(prescale)
  );

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;

  // Reset at the start: every testbench, baseline and gold resets first, and
  // the RTL's register initialisers equal its reset values.
  always @(*) if (init) assume(rst);

  // prescale in 1..4: keeps a bit period at 8..32 clocks so frames fit the
  // bound. A bound on the search, not a spec rule (README: prescale =
  // Fclk / (baud * 8), any 16-bit value); items that need a large prescale
  // (T2: 16'hFFFF) are out of bound by construction.
  always @(*) assume(prescale >= 16'd1 && prescale <= 16'd4);

  // prescale constant while busy: the README describes it as a configuration
  // input set for a baud rate; changing it mid-frame is not legal stimulus.
  always @(posedge clk) if (!init && $past(busy)) assume(prescale == $past(prescale));

  // AXIS source rules (ARM IHI 0051B):
  // s2.8.2: TVALID is driven low during reset.
  always @(*) if (rst) assume(!s_axis_tvalid);
  // s2.2.1: once TVALID is asserted it stays asserted, and TDATA stays stable,
  // until the handshake (TVALID && TREADY). A reset ends the obligation.
  always @(posedge clk)
    if (!init && !rst && !$past(rst) && $past(s_axis_tvalid && !s_axis_tready))
      assume(s_axis_tvalid && s_axis_tdata == $past(s_axis_tdata));
endmodule
