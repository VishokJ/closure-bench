// Fixed-seed random-stimulus testbench for uart_tx (not a gate; tools/check
// reports which plan items it hits, i.e. which are reachable by accident).
//
// Legal AXI-Stream stimulus only, chosen at random from an in-testbench
// xorshift32 (not $urandom, whose sequence depends on the simulator version):
// tvalid raised at random with random data, held stable until the handshake
// (AXIS 2.2.1), random gaps, rare resets with tvalid low (AXIS 2.8.2), and
// prescale 1..8 changed only while the transmitter is idle. No checks.
`timescale 1ns / 1ps

module tb_rand_tx;

  localparam int CLK_PERIOD = 8;
  localparam int CYCLES = 120000;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic [7:0]  s_axis_tdata = 8'd0;
  logic        s_axis_tvalid = 1'b0;
  logic [15:0] prescale = 16'd5;
  wire         s_axis_tready;
  wire         txd, busy;

  always #(CLK_PERIOD / 2) clk = ~clk;

  uart_tx #(.DATA_WIDTH(8)) dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .txd(txd), .busy(busy),
    .prescale(prescale)
  );

  function automatic logic [31:0] xorshift(input logic [31:0] x);
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return x;
  endfunction

  logic [31:0] s = 32'h2545_F491;
  logic [7:0]  p_valid = 8'd128;  // chance in 256 of raising tvalid per idle cycle

  // Drive on the falling edge; the handshake is the value sampled at the
  // previous rising edge, which is what the DUT saw.
  logic hs = 1'b0;
  always @(posedge clk) hs <= s_axis_tvalid && s_axis_tready && !rst;

  initial begin
    rst = 1'b1; repeat (4) @(negedge clk);
    rst = 1'b0;
    for (int c = 0; c < CYCLES; c++) begin
      @(negedge clk);
      s = xorshift(s);
      if (rst) begin
        rst = 1'b0;
      end else if (s[31:22] == 0) begin       // ~1 in 1024: reset, tvalid low
        rst = 1'b1;
        s_axis_tvalid = 1'b0;
      end else begin
        if (hs) s_axis_tvalid = 1'b0;
        if (!s_axis_tvalid && s[7:0] < p_valid) begin
          s_axis_tvalid = 1'b1;
          s_axis_tdata = s[15:8];
        end
        if (s[21:12] == 0) p_valid = s[29:22];  // occasionally change the offered load
        if (!busy && !s_axis_tvalid && s[21:16] == 6'd1) prescale = 16'(1 + s[24:22]);
      end
    end
    // A word still offered waits for its handshake before tvalid drops (AXIS 2.2).
    if (s_axis_tvalid) begin
      do @(negedge clk); while (!hs);
      s_axis_tvalid = 1'b0;
    end
    repeat (200) @(negedge clk);
    $finish;
  end

endmodule
