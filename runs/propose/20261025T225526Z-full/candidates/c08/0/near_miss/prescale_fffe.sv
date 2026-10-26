`timescale 1ns / 1ps

module tb;

  // One below the maximum: the same frame, but prescale bit 0 is clear,
  // so the stop-bit reload is 19'h7FFF0 instead of 19'h7FFF8.
  localparam logic [15:0] PRESCALE = 16'hFFFE;
  localparam int BIT = 65534 * 8;  // 524272 clocks per bit

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic [7:0]  s_axis_tdata = 8'h00;
  logic        s_axis_tvalid = 1'b0;
  logic [15:0] prescale = 16'd0;
  wire         s_axis_tready;
  wire         txd;
  wire         busy;

  always #4 clk = ~clk;

  uart_tx dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .txd(txd), .busy(busy),
    .prescale(prescale)
  );

  task automatic hold_check(input logic exp_txd, input int n, input string what);
    for (int i = 0; i < n; i++) begin
      if (txd !== exp_txd) $fatal(1, "%s: txd=%b expected %b at cycle %0d", what, txd, exp_txd, i);
      if (s_axis_tready !== 1'b0) $fatal(1, "%s: tready high during frame at cycle %0d", what, i);
      if (busy !== 1'b1) $fatal(1, "%s: busy low during frame at cycle %0d", what, i);
      @(negedge clk);
    end
  endtask

  logic [7:0] data = 8'h5A;
  int guard;

  initial begin
    prescale = PRESCALE;
    @(negedge clk);
    rst = 1'b1; repeat (3) @(negedge clk);
    rst = 1'b0;

    guard = 0;
    while (s_axis_tready !== 1'b1) begin
      @(negedge clk);
      guard++;
      if (guard > 20) $fatal(1, "tready never rose after reset");
    end
    if (txd !== 1'b1) $fatal(1, "txd not idle high");

    s_axis_tdata  = data;
    s_axis_tvalid = 1'b1;
    @(negedge clk);
    s_axis_tvalid = 1'b0;
    s_axis_tdata  = 8'h00;

    hold_check(1'b0, BIT, "start bit");
    for (int b = 0; b < 8; b++) hold_check(data[b], BIT, $sformatf("data bit %0d", b));
    hold_check(1'b1, BIT + 1, "stop bit");

    if (s_axis_tready !== 1'b1) $fatal(1, "tready did not return after stop bit");
    @(negedge clk);
    if (busy !== 1'b0) $fatal(1, "busy still high after frame");
    if (txd !== 1'b1) $fatal(1, "txd not idle after frame");

    prescale = 16'd0;
    repeat (4) @(negedge clk);
    $display("NEAR-MISS done: 0x%02h transmitted at prescale 0x%04h", data, PRESCALE);
    $finish;
  end

  initial begin
    #200ms;
    $fatal(1, "timeout");
  end

endmodule
