`timescale 1ns / 1ps

// Same mid-frame reset, but issued late in the start bit when prescale_reg
// has already counted down to 11 (not above 16).
module tb;

  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic [7:0]  s_axis_tdata = 8'h00;
  logic        s_axis_tvalid = 1'b0;
  logic [15:0] prescale = 16'd5;
  wire         s_axis_tready;
  wire         txd;
  wire         busy;

  always #4 clk = ~clk;

  uart_tx dut (
    .clk(clk), .rst(rst),
    .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid),
    .s_axis_tready(s_axis_tready),
    .txd(txd), .busy(busy), .prescale(prescale)
  );

  task automatic wait_clks(input int n);
    repeat (n) @(negedge clk);
  endtask

  initial begin
    wait_clks(2);
    rst = 1'b1; wait_clks(2);
    rst = 1'b0; wait_clks(4);
    if (s_axis_tready !== 1'b1) $fatal(1, "tready not high when idle");

    s_axis_tdata  = 8'hA5;
    s_axis_tvalid = 1'b1;
    @(negedge clk);
    s_axis_tvalid = 1'b0;
    if (busy !== 1'b1) $fatal(1, "busy not set after accept");
    if (txd !== 1'b0) $fatal(1, "start bit not driven");

    // late in the start bit: prescale_reg = 39-28 = 11
    wait_clks(28);
    if (busy !== 1'b1 || txd !== 1'b0) $fatal(1, "not mid start bit");
    if (s_axis_tready !== 1'b0) $fatal(1, "tready high mid-frame");

    rst = 1'b1;
    wait_clks(2);
    if (s_axis_tready !== 1'b0) $fatal(1, "tready not cleared in reset");
    rst = 1'b0;

    @(negedge clk);
    if (s_axis_tready !== 1'b1)
      $fatal(1, "tready did not rise on first clock after reset release");
    if (txd !== 1'b1 || busy !== 1'b0) $fatal(1, "not idle after reset");

    wait_clks(5);
    $display("near-miss done");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end

endmodule
